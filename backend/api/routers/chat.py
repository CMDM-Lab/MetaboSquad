from fastapi import APIRouter, HTTPException, Request
import uuid
from datetime import datetime, timedelta, timezone
from api.artifacts import UPLOAD_ROOT, resolve_uploads_path
from api.database import SessionDep
from sqlmodel import Field, SQLModel, select
from typing import Any, Optional
from pydantic import BaseModel
from sqlalchemy import Column, text
from langchain_core.messages import AIMessage
from sqlalchemy.dialects.postgresql import JSONB 
from pathlib import Path
import json
import asyncio
import time
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import traceback

# Create a router
router = APIRouter(
    prefix="/api/chat", # prefix: path prefix for every route below
    tags=["chat"], # tags: labels used to group routes in Swagger UI
    responses={404: {"description": "Not found"}}, # responses: shared error responses
)

# Default title for a new chat. `add_chat` writes this value, and `continue_chat` also uses it to
# decide "this chat has not been named yet". The two places used to hard-code two different
# strings, so the "use the first message as the title" branch never ran -- every chat stayed
# at the default title. A single constant means the two sides can no longer drift.
# Guarded by tests/test_chat_titles.py.
DEFAULT_CHAT_TITLE = "新對話"

# Time window (seconds) for the duplicate-request early return. See the check in chat_with_agent below.
# It guards against replays of the form "the answer just landed and the same message is sent again";
# limiting it to a window means a physician who deliberately re-asks the same question later is
# not mistaken for a duplicate and left without a fresh answer forever.
DUPLICATE_REQUEST_WINDOW_SEC = 10

# Structured state fields to send to the frontend (the graph is unchanged; they are just no longer discarded)
STRUCTURED_KEYS = (
    "analysis_result",
    "review_result",
    "id_mapping_result",
    "literature_result",
    "significant_metabolites",
    "sig_all",  # All significant features (named + bare m/z); see state.py for how it
    # differs from significant_metabolites. Like significant_metabolites it is a
    # list, and an empty list means "ran, no significant features" -- the same "keep empty list" rule
    # (payload loop below) applies to it.
)


def _json_fallback(o):
    """numpy scalars have .item() and are converted back to native Python numbers; other types fall back to str."""
    return o.item() if hasattr(o, "item") else str(o)


def _within_duplicate_window(answered_at: datetime) -> bool:
    """Whether the previous answer falls inside the duplicate-request early-return window.

    `ChatMessage.created_at` is TIMESTAMP WITHOUT TIME ZONE and is written with
    `datetime.now(timezone.utc)`; PostgreSQL drops the tzinfo, so it reads back as
    naive UTC. Subtracting it from an aware now raises TypeError, so tzinfo is added first.
    """
    if answered_at.tzinfo is None:
        answered_at = answered_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - answered_at
    return age <= timedelta(seconds=DUPLICATE_REQUEST_WINDOW_SEC)


def _normalize_result_file_path(raw: str) -> str:
    """The path format in `analysis_result["result_files"]` is unstable
    (`recommend_and_analysis` in `use_tool/code.py` is in the frozen zone): it computes
    relative paths from the monorepo root (the parent of `backend/`), so they often carry a
    `/backend/uploads/...` prefix instead of a clean `/uploads/...` or
    `uploads/...`. Find where "uploads/" occurs and take everything from there, ignoring any prefix
    (`/backend/`, absolute system paths, etc.); if it is not found, return the input unchanged and let
    `resolve_uploads_path` decide whether it escapes the root.
    """
    idx = raw.find("uploads/")
    if idx == -1:
        return raw
    return raw[idx:]


def _verified_output_folder(reported: str, analysis_result: dict | None = None) -> str:
    """The output_file_path reported by the graph sometimes points to the wrong subdirectory
    (`analysis_graph.py` writes to `analysis/` but reports `literature/`, a copy-paste bug in the
    frozen zone). A wrong path leaves the full report, the file list and the ZIP all empty, with
    no error message; the physician just assumes the node failed -- so it is verified here before use.

    Tried in order (each level has an explicit fallback, so no level fails without a signal):
    1. The reported path itself exists -> use it as is.
    2. `analysis_result["result_files"]` is non-empty -> take the dirname of the first file,
       verify it exists -> use it. This is the most reliable signal on the success path: the real
       output folder name is `{csv filename}_{%Y%m%d_%H%M%S}` (`use_tool/code.py`), which does not
       match the `%Y-%m-%d-%H-%M-%S` date in the reported value, so the date glob below gets 0 hits
       in this case -- which is exactly why the old date-glob-only version could not fix the success path.
    3. The last segment of the reported path (the date) has exactly one match under
       uploads/output/*/<date> -> use it (covers the case where `result_dir` returns early with no result_files).
    4. Otherwise keep the original value (so the downstream 404 message still appears; never silently substitute something wrong).

    Timing constraint: `analysis_result` is only available after the whole agent run finishes
    (the `STRUCTURED_KEYS` result event enters the queue after the status/`output_file_path`
    event), so when the `output_file_path` status event first appears and zip_ready is about to
    be sent, only levels 1 and 3 are usable. The caller calls this function again after
    `analysis_result` arrives and before DB persistence, and that is when level 2 comes into play
    (see the second call in `continue_chat` and its comment).
    """
    try:
        resolved = resolve_uploads_path(reported)
    except ValueError:
        # Path escapes the root: not this function's responsibility; leave it to the downstream
        # (/api/artifacts) to reject at the same security boundary. Here we only make sure no exception breaks the SSE.
        return reported

    if resolved.is_dir():
        return reported

    if analysis_result:
        result_files = analysis_result.get("result_files")
        if isinstance(result_files, list) and result_files:
            first = result_files[0]
            if isinstance(first, str) and first:
                candidate_dir = str(Path(_normalize_result_file_path(first)).parent)
                try:
                    resolved_candidate = resolve_uploads_path(candidate_dir)
                    if resolved_candidate.is_dir():
                        return f"uploads/{resolved_candidate.relative_to(UPLOAD_ROOT).as_posix()}"
                except ValueError:
                    # result_files gave an out-of-bounds or malformed path: not fatal,
                    # move on to the next strategy (date glob).
                    pass

    date_segment = Path(reported.rstrip("/")).name
    if date_segment:
        matches = [p for p in UPLOAD_ROOT.glob(f"output/*/{date_segment}") if p.is_dir()]
        if len(matches) == 1:
            return f"uploads/{matches[0].relative_to(UPLOAD_ROOT).as_posix()}"

    return reported


# Chat record table
class Chat(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    thread_id: str = Field(index=True, unique=True)
    title: str = Field(default=DEFAULT_CHAT_TITLE)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # A column could be added to record the last update time, for sorting the sidebar
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # Foreign key to Chat's thread_id
    thread_id: str = Field(foreign_key="chat.thread_id", index=True)
    role: str  # "user" or "assistant"
    content: Any = Field(sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Reserved metadata for token counts or tool-call information
    # metadata: dict = Field(default_factory=dict, sa_column=Column(JSONB))

# Defines the incoming chat content
class ChatRequest(BaseModel):
    message: str
    file_path: str | None = None

# Defines the returned content
class ChatPublic(BaseModel):
    thread_id: str
    title: str
    created_at: datetime

# Defines the editable fields
class ChatUpdate(SQLModel):
    title: Optional[str] = None

# Defines the returned chat list
class ChatListResponse(BaseModel):
    success: bool
    chats: list[ChatPublic] 


def process_file_for_agent(file_path: str):
    if not file_path:
        return None

    normalized = file_path.replace("\\", "/")

    # Normalise to a path relative to uploads
    if normalized.startswith("/uploads/"):
        rel_path = normalized.removeprefix("/uploads/").lstrip("/")
    else:
        # If it is an absolute or other path -> try to convert it to a path relative to uploads
        try:
            rel_path = str(Path(normalized).relative_to("uploads"))
        except ValueError:
            rel_path = Path(normalized).name

    return {
        "type": "file_path",
        "data": rel_path
    }


# Image file extensions: decide which prefix `_graph_file_path` uses (see that function's docstring).
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _graph_file_path(rel_path: str) -> str:
    """Convert a path relative to uploads into a format "that subgraph can open".

    The two subgraphs resolve `files[0]` in completely different ways, so no single string can satisfy
    both; the only option is to branch on the extension. Both are in the frozen zone (`src/graph_agent/`) and cannot be changed:

    - **Images** -> `uploads/image/x.png`
      `_load_image_as_base64` in `graph/plot_graph.py` uses a bare `open(path)`,
      i.e. relative to the process CWD, and uvicorn's CWD is `backend/`.

    - **CSV** -> `../../uploads/csv/x.csv`
      `extract_schema_and_config` in `use_tool/code.py` uses
      `BASE_DIR = Path(__file__).resolve().parent.parent` (=
      `backend/src/graph_agent`) to build the path, and there is no uploads under it. Of four formats
      tested, only `../../uploads/...` finds the file.
      This value is also passed verbatim into `config_by_data["file_path"]` and on to the R script;
      the container's `working_dir` is `/workspace` and uploads is mounted at `/uploads`,
      so `/workspace/../../uploads/...` resolves to exactly `/uploads/...`, which means the R side
      is correct too.

    `tests/test_chat_files_channel.py` has a tripwire pinning both assumptions: if the frozen zone's
    path resolution is ever fixed, the test goes red and says to come back and change this.
    """
    if Path(rel_path).suffix.lower() in _IMAGE_SUFFIXES:
        return f"uploads/{rel_path}"
    return f"../../uploads/{rel_path}"

@router.get("/{thread_id}/history", response_model=list[ChatMessage])
async def get_chat_history(thread_id: str, session: SessionDep, request: Request):
    statement = (
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = session.exec(statement).all()
    
    if not messages:
        return []
        
    return messages

# Response format
# [
#   {
#     "id": 1,
#     "thread_id": "session_abc_123",
#     "role": "user",
#     "content": "Please analyse the PCA plot of this metabolomics dataset.",
#     "created_at": "2026-03-25T11:20:00Z"
#   },
#   {
#     "id": 2,
#     "thread_id": "session_abc_123",
#     "role": "assistant",
#     "content": "No problem! Please upload your data file...",
#     "created_at": "2026-03-25T11:20:05Z"
#   }
# ]

# Continue an existing chat
@router.post("/{thread_id}")
async def continue_chat(thread_id: str, req: ChatRequest, session: SessionDep,
                        request: Request):
    # Prefer the thread_id from the path
    statement = select(Chat).where(Chat.thread_id == thread_id)
    chat_db = session.exec(statement).first()
    # If the title is still the default, use the first few characters of the first message as the title
    if chat_db and chat_db.title == DEFAULT_CHAT_TITLE:
        chat_db.title = req.message[:20] 
        session.add(chat_db)
        session.commit()
    

    # Get the required connections and agent from the lifespan's app.state
    main_agent = request.app.state.main_agent # assumes it has been mounted

    # --- Key part 1: prepare standard-conforming content (content list) ---
    content_list = []

    processed_result = process_file_for_agent(req.file_path)
    # Prepare the content sent to the agent
    content_list = [{"type": "text", "text": req.message}]

    # Note: the `file_path` type no longer appends a text hint to the message body.
    # This used to add
    #     [a system hint saying the user uploaded a file located at: csv/lcms_table.csv]
    # which was the only way to pass the path back when the `files` channel was not populated. Now the path goes through `files`
    # (see graph_files below), so that text is redundant, and it would show up in two places the physician can see:
    # their **own message bubble** in the chat (the text is stored in ChatMessage),
    # and the "original research question" field of the plot_review report.
    # The graph has its own mechanism for adding the path -- `input_verifier_node` in `supervisor.py`
    # appends a line noting the automatically added upload path when the message does not mention a file; that is
    # its intended design, and we do not need to inject it again from outside.
    # Guarded by tests/test_chat_files_channel.py.
    if processed_result and processed_result["type"] == "image":
        # Multimodal image format. `process_file_for_agent` currently never returns "image"
        # (it always returns "file_path"), so this branch is unreachable for now; it is kept because multimodal
        # input is part of the existing contract and will be used once process_file_for_agent's classification changes.
        content_list.append({
            "type": "image_url",
            "image_url": {"url": processed_result["data"]}
        })

    # The graph's `files` channel. This line must not be dropped: when `files` is empty,
    # `_correct_misclassification` in `supervisor.py` **forcibly downgrades** the analysis and
    # plot_review intents to direct (plain chat). Without it, those two requests
    # only ever get a "please wait, analysing now" reply and nothing else happens.
    # For why the path format looks the way it does, see `_graph_file_path`.
    graph_files = (
        [_graph_file_path(processed_result["data"])]
        if processed_result and processed_result["type"] == "file_path"
        else []
    )

    # Avoid writing the same answer twice due to duplicate requests:
    # if the last two messages are [assistant, user], user.content equals this input,
    # and that answer landed "just now" (within DUPLICATE_REQUEST_WINDOW_SEC),
    # the previous identical request has just completed, so return the existing answer directly.
    #
    # The time window was added later: originally only the content was compared, with no time condition, so
    # "a given question could only ever be asked once per thread". In practice, after a literature search first
    # returned 0 papers because NCBI_KEY was empty, a physician asking the same question again only got the
    # old 0-paper answer and the agent was never invoked -- "once it fails, it can never be rerun".
    # The comment always said "just completed"; the implementation simply did not honour it.
    #
    # created_at is TIMESTAMP WITHOUT TIME ZONE and is written with
    # datetime.now(timezone.utc), so it reads back as naive UTC; tzinfo must be added
    # before comparing.
    recent_statement = (
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(2)
    )
    recent_messages = session.exec(recent_statement).all()
    if (
        len(recent_messages) == 2
        and recent_messages[0].role == "assistant"
        and recent_messages[1].role == "user"
        and recent_messages[1].content == content_list
        and _within_duplicate_window(recent_messages[0].created_at)
    ):
        return {
            "status": "success",
            "thread_id": thread_id,
            "AI_messages": recent_messages[0].content
        }
    
    # 2. Save the user message
    user_msg = ChatMessage(thread_id=thread_id, role="user", content=content_list)
    session.add(user_msg)
    session.commit() # Commit once first to make sure the user message is stored

    # --- Build the SSE event generator ---
    async def sse_event_generator() -> AsyncGenerator[str, None]:
        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def stream_writer(data: dict):
            # Thread-safe version
            loop.call_soon_threadsafe(queue.put_nowait, data)

        # Buffers the full AI reply, which is saved to the database at the end
        full_ai_content = ""
        structured_payload: dict | None = None
        structured_intent: str | None = None
        trace_steps: list[dict] = []
        status_seq = 0
        # zip_ready only occurs during live streaming and no longer exists when history is reloaded;
        # record it and persist it with the result block so the "files" tab still works after a reload.
        last_output_folder: str | None = None
        # I2: when the graph reports output_file_path, analysis_result is not yet available
        # (see the timing note on _verified_output_folder), so keep a copy of the raw
        # reported value here and correct the persisted folder again once structured_payload arrives.
        raw_output_file_path: str | None = None

        # Per-step timing for the trace table (Task 6). `status` events mark
        # a step *starting*, so the interval that ends when step N+1's
        # `status` arrives is step N's duration — the wall-clock the
        # user actually waited, measured where it crosses the SSE
        # boundary. `last_status_at` is updated each time a status closes an
        # interval; `last_ms` (below, after the loop) closes the final step
        # when the stream ends, the same way `saved`'s `last_ms` does for
        # the live client.
        stream_started = time.monotonic()
        last_status_at = stream_started

        config = {
            "configurable": {
                "thread_id": thread_id,
                "writer": stream_writer,
            }
        }

        # Run LangGraph asynchronously in the background so the SSE connection is not blocked
        async def run_agent():
            nonlocal full_ai_content, structured_payload, structured_intent
            try:
                # Use asyncio.to_thread to run the synchronous main_agent.invoke in a background thread
                result = await asyncio.to_thread(
                    main_agent.invoke,
                    {
                        "messages": [{"role": "user", "content": content_list}],
                        "files": graph_files,
                    },
                    config=config
                )

                # After completion, extract the full assistant reply from the final result
                if "messages" in result and result["messages"]:
                    last_msg = result["messages"][-1]
                    if isinstance(last_msg, AIMessage) and last_msg.content:
                        full_ai_content = last_msg.content
                        # Push a text event so the frontend can render the final text
                        await queue.put({"text": full_ai_content})

                # Drop None and empty dicts but keep empty lists; this asymmetry is deliberate:
                # among these six keys, the dict ones are "result objects", and an empty dict means the node produced nothing,
                # which the frontend cannot tell apart from "did not run" (neither is shown), so no information is lost;
                # whereas significant_metabolites and sig_all are lists, and their being "empty"
                # is itself a finding ("analysis complete, no significant metabolites/features found");
                # dropping it would make the physician think the analysis did not run.
                payload = {}
                for k in STRUCTURED_KEYS:
                    v = result.get(k)
                    if v is None or v == {}:
                        continue
                    payload[k] = v

                if payload:
                    try:
                        # numpy types / Path objects cannot go into JSONB directly, nor through
                        # json.dumps. Sanitise once at the source so the SSE and DB writes share
                        # the same copy, avoiding protection on only one side.
                        payload = json.loads(json.dumps(payload, default=_json_fallback))
                    except (TypeError, ValueError) as ser_err:
                        # Give up only the structured fields; the text reply is still sent. Do not let this escape to
                        # the outer except, otherwise it masquerades as an agent crash and the frontend shows an
                        # error message unrelated to what happened (the analysis actually succeeded; only the format was abnormal).
                        print(f"⚠️ 結構化結果無法序列化，本次略過: {ser_err}")
                        payload = {}

                    if payload:
                        structured_payload = payload
                        structured_intent = result.get("intent")
                        await queue.put({"result": payload, "intent": structured_intent})

            except Exception as e:
                print(f"❌ LangGraph 同步執行崩潰: {str(e)}")
                traceback.print_exc()
                await queue.put({"error": str(e)})
            finally:
                # Make sure the end signal is always pushed
                await queue.put({"done": True})

        # Start the background task
        agent_task = asyncio.create_task(run_agent())

        # Start listening on the queue and yield to the frontend
        while True:
            await asyncio.sleep(0.01)
            item = await queue.get()
            
            try:
                # 1. Detect the end sentinel finally emitted by run_agent
                if "done" in item:
                    break

                # 2. Detect and handle the original text chunks (emitted from the final result) so the frontend can see the reply text
                if "text" in item:
                    yield f"event: text\ndata: {json.dumps({'content': item['text']})}\n\n"

                if "result" in item:
                    yield ("event: result\ndata: "
                           + json.dumps({"intent": item.get("intent"),
                                         "data": item["result"]}, default=str)
                           + "\n\n")

                if "error" in item:
                    yield f"event: error\ndata: {json.dumps({'content': item['error']})}\n\n"

                # Only detect the statuses we need
                if "status" in item:
                    now = time.monotonic()
                    status_seq += 1
                    status_payload = {"content": item["status"], "seq": status_seq}
                    if status_seq > 1:
                        # This status closes the interval that began when
                        # step seq-1 was announced. Stamp the *previous*
                        # trace entry before appending the new one below —
                        # reversed, every duration lands on the wrong step.
                        prev_ms = int((now - last_status_at) * 1000)
                        trace_steps[-1]["ms"] = prev_ms
                        status_payload["prev_ms"] = prev_ms
                    last_status_at = now
                    trace_steps.append({"seq": status_seq, "raw": item["status"]})
                    yield ("event: status\ndata: "
                           + json.dumps(status_payload)
                           + "\n\n")

                    # Also detect the output file path. Only keep the raw value; zip_ready is sent after the loop
                    # ends and the folder has had its final correction (see below).
                    if "output_file_path" in item:
                        raw_output_file_path = item["output_file_path"]

            finally:
                # Release normally after every item, never break the loop
                queue.task_done()

        # --- Successfully exited the while True loop ---

        # Close the final step: no further `status` will arrive to do it,
        # so the stream boundary itself is the closing edge. Stamped onto
        # `trace_steps[-1]["ms"]` *before* persistence below, or the stored
        # trace is missing exactly one duration — the last one, which is
        # usually the longest (see Task 6 brief, "Why prev_ms and not ms").
        last_ms: int | None = None
        if trace_steps:
            last_ms = int((time.monotonic() - last_status_at) * 1000)
            trace_steps[-1]["ms"] = last_ms

        # I2: analysis_result (if any) is only settled here; it carries the result_files signal, which is
        # more reliable than the date segment, and is used for a final correction of the folder.
        #
        # zip_ready is deliberately held until this moment. It used to be sent immediately with the
        # `output_file_path` status event, but analysis_result had not entered the queue yet,
        # leaving only levels 1 and 3 of `_verified_output_folder` -- the real folder on the success path
        # is named `{csv filename}_{%Y%m%d_%H%M%S}`, which does not match the reported `%Y-%m-%d-%H-%M-%S`,
        # so the date glob always got 0 hits and the wrong literature value was sent as is,
        # and the download button always returned 404 (measured 2026-08-12). SSE is one-way and cannot be amended once sent, so
        # the only fix is to send later, not to send and then correct.
        #
        # The cost is that the download button appears a few hundred milliseconds later; nothing is downloadable before the analysis finishes anyway.
        # Guarded jointly by test_zip_ready_uses_the_result_files_corrected_folder and
        # test_zip_ready_precedes_saved (the value must be right, and it must still come before saved).
        if raw_output_file_path:
            analysis_result_for_folder = (
                structured_payload.get("analysis_result") if structured_payload else None
            )
            last_output_folder = _verified_output_folder(
                raw_output_file_path, analysis_result_for_folder)
            yield f"event: zip_ready\ndata: {json.dumps({'folder_name': last_output_folder})}\n\n"

        # 5. After the stream has fully ended, write the full AI reply to the database
        if full_ai_content or structured_payload or trace_steps:
            try:
                blocks: list[dict] = []
                if full_ai_content:
                    blocks.append({"type": "text", "text": full_ai_content})
                if structured_payload:
                    blocks.append({"type": "result", "intent": structured_intent,
                                   "data": structured_payload,
                                   "folder": last_output_folder})
                if trace_steps:
                    blocks.append({"type": "trace", "steps": trace_steps})

                new_ai_msg = ChatMessage(thread_id=thread_id, role="assistant",
                                         content=blocks)
                session.add(new_ai_msg)
                session.commit()
                session.refresh(new_ai_msg)
                print("💾 [SQLModel] AI 回覆已成功持久化至資料庫中。")

                if full_ai_content or structured_payload:
                    saved_payload: dict = {"message_id": new_ai_msg.id}
                    if last_ms is not None:
                        saved_payload["last_ms"] = last_ms
                    yield ("event: saved\ndata: "
                           + json.dumps(saved_payload) + "\n\n")
                # Only a trace (the agent crashed midway, e.g. an R script exited non-zero) ->
                # deliberately do not send saved: saved only means a complete answer has been stored.
                # The message itself is still stored, keeping the crash trace for debugging.
            except Exception as db_err:
                session.rollback()
                print(f"❌ 寫入資料庫失敗: {db_err}")
                yield ("event: error\ndata: "
                       + json.dumps({"content": f"回覆儲存失敗：{db_err}"})
                       + "\n\n")

    # Return a standard SSE streaming response
    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")


# 1. Add a chat (initialise the sidebar entry)
@router.post("/", response_model=ChatPublic)
def add_chat(session: SessionDep):
    new_id = str(uuid.uuid4())
    new_chat = Chat(
            thread_id=new_id,
            title=DEFAULT_CHAT_TITLE,
        )
    session.add(new_chat)
    session.commit()
    session.refresh(new_chat)
        
    # 3. Return to the frontend, which immediately navigates to /chats/{new_id}
    return new_chat

# 2. Delete a chat (key point: also delete the AI memory)
@router.delete("/{thread_id}")
def delete_chat(thread_id: str, session: SessionDep):
    # Look up the chat in the business table
    statement = select(Chat).where(Chat.thread_id == thread_id)
    chat_db = session.exec(statement).first()

    if not chat_db:
        raise HTTPException(status_code=404, detail="對話不存在")

    try:
        # --- Added: delete the associated chat records (ChatMessage) first ---
        # This resolves the ForeignKeyViolation error
        session.execute(
            text("DELETE FROM chatmessage WHERE thread_id = :tid"), 
            {"tid": thread_id}
        )

        # B. Delete the business table record (Chat)
        session.delete(chat_db)
        
        # C. Clean up LangGraph checkpoints (memory)
        queries = [
            "DELETE FROM checkpoints WHERE thread_id = :tid",
            "DELETE FROM checkpoint_blobs WHERE thread_id = :tid",
            "DELETE FROM checkpoint_writes WHERE thread_id = :tid"
        ]
        
        for q in queries:
            session.execute(text(q), {"tid": thread_id})
            
        # Commit everything together
        session.commit()
        
    except Exception as e:
        session.rollback()
        print(f"刪除失敗: {e}")
        raise HTTPException(status_code=500, detail="刪除過程發生錯誤")

    return {"status": "success", "message": f"已成功刪除對話 {thread_id} 及其所有關聯資料"}

# 3. Get the chat list (for the sidebar)
@router.get("/", response_model= ChatListResponse)
def list_chat(session: SessionDep):
    # Sort so the newest chat is on top
    statement = select(Chat).order_by(Chat.created_at.desc())
    chats = session.exec(statement).all()

    return {
        "success": True,
        "chats": chats # SQLModel converts this to the ChatPublic format automatically
    }

# 4. Edit the title
@router.patch("/{thread_id}", response_model=ChatPublic)
def update_chat(thread_id: str, chat_update: ChatUpdate, session: SessionDep):
    statement = select(Chat).where(Chat.thread_id == thread_id)
    chat_db = session.exec(statement).first()
    if not chat_db:
        raise HTTPException(status_code=404, detail="對話不存在")
    
    # Only update the fields that were passed in (exclude_unset=True)
    update_data = chat_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(chat_db, key, value)

    session.add(chat_db)    
    session.commit()
    session.refresh(chat_db)
    return chat_db
