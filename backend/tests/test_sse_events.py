"""SSE event tests. A fake agent replaces LangGraph, so no OpenAI key is needed."""

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from langchain_core.messages import AIMessage
from sqlmodel import select

from api.artifacts import UPLOAD_ROOT
from api.routers.chat import Chat, ChatMessage


class FakeAgent:
    """Simulate main_agent: emit two status events via the writer, then return a result with structured fields."""

    def invoke(self, payload, config=None):
        writer = config["configurable"]["writer"]
        writer({"status": "Parameter extraction complete, statistical analysis in progress."})
        writer({"status": "Summary complete! Ready to download.",
                "output_file_path": "uploads/output/analysis/2026-01-01"})
        return {
            "messages": [AIMessage(content="分析完成")],
            "intent": "analysis",
            "analysis_result": {"r_code": "t.test(x, y)", "success": True},
            "significant_metabolites": ["citrate", "lactate"],
        }


@pytest.fixture(name="chat_client")
def chat_client_fixture(session):
    from fastapi.testclient import TestClient

    from api.database import get_session
    from main import create_app

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        c.app.state.main_agent = FakeAgent()
        yield c
    app.dependency_overrides.clear()


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for chunk in text.split("\n\n"):
        if not chunk.strip():
            continue
        event_name, data = "message", None
        for line in chunk.split("\n"):
            if line.startswith("event: "):
                event_name = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((event_name, data))
    return events


def _prepare(session) -> str:
    session.commit()
    chat = Chat(thread_id="th-sse", title="新聊天")
    session.add(chat)
    session.commit()
    return "th-sse"


def test_emits_result_event_with_structured_data(chat_client, session):
    tid = _prepare(session)
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    events = _parse_sse(res.text)

    result_events = [d for name, d in events if name == "result"]
    assert len(result_events) == 1
    assert result_events[0]["intent"] == "analysis"
    assert result_events[0]["data"]["analysis_result"]["r_code"] == "t.test(x, y)"
    assert result_events[0]["data"]["significant_metabolites"] == ["citrate", "lactate"]


def test_status_events_carry_incrementing_seq(chat_client, session):
    tid = _prepare(session)
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    seqs = [d["seq"] for name, d in _parse_sse(res.text) if name == "status"]
    assert seqs == [1, 2]


def test_status_event_content_field_still_present(chat_client, session):
    """The existing frontend reads status.content; adding seq must not displace it."""
    tid = _prepare(session)
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    status_events = [d for name, d in _parse_sse(res.text) if name == "status"]
    assert status_events[0]["content"] == (
        "Parameter extraction complete, statistical analysis in progress."
    )
    assert status_events[1]["content"] == "Summary complete! Ready to download."


def test_emits_saved_event_with_real_message_id(chat_client, session):
    tid = _prepare(session)
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})

    saved = [d for name, d in _parse_sse(res.text) if name == "saved"]
    assert len(saved) == 1

    msg = session.exec(
        select(ChatMessage)
        .where(ChatMessage.thread_id == tid)
        .where(ChatMessage.role == "assistant")
    ).one()
    assert saved[0]["message_id"] == msg.id


def test_persists_content_blocks_with_text_result_and_trace(chat_client, session):
    tid = _prepare(session)
    chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})

    msg = session.exec(
        select(ChatMessage)
        .where(ChatMessage.thread_id == tid)
        .where(ChatMessage.role == "assistant")
    ).one()

    blocks = msg.content
    assert isinstance(blocks, list)
    by_type = {b["type"]: b for b in blocks}
    assert by_type["text"]["text"] == "分析完成"
    assert by_type["result"]["intent"] == "analysis"
    assert len(by_type["trace"]["steps"]) == 2
    assert by_type["trace"]["steps"][0]["seq"] == 1
    assert "Parameter extraction" in by_type["trace"]["steps"][0]["raw"]


def test_result_event_keeps_empty_significant_metabolites_list(chat_client, session):
    """Ruling 1: an empty list is a meaningful result (analysis finished, no significant
    metabolites found) and must not be filtered out by truthiness."""
    tid = _prepare(session)

    class EmptyMetabolitesAgent:
        def invoke(self, payload, config=None):
            return {
                "messages": [AIMessage(content="未發現顯著代謝物")],
                "intent": "analysis",
                "significant_metabolites": [],
            }

    chat_client.app.state.main_agent = EmptyMetabolitesAgent()
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    events = _parse_sse(res.text)
    result_events = [d for name, d in events if name == "result"]
    assert len(result_events) == 1
    assert "significant_metabolites" in result_events[0]["data"]
    assert result_events[0]["data"]["significant_metabolites"] == []


def test_result_event_excludes_none_keys(chat_client, session):
    """Ruling 1: None or a missing key means the node did not run and should be excluded;
    only an analysis_result that was actually returned appears in data."""
    tid = _prepare(session)

    class PartialResultAgent:
        def invoke(self, payload, config=None):
            return {
                "messages": [AIMessage(content="分析完成")],
                "intent": "analysis",
                "analysis_result": {"r_code": "t.test(x, y)", "success": True},
                "review_result": None,
                "literature_result": None,
            }

    chat_client.app.state.main_agent = PartialResultAgent()
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    events = _parse_sse(res.text)
    result_events = [d for name, d in events if name == "result"]
    assert len(result_events) == 1
    assert set(result_events[0]["data"].keys()) == {"analysis_result"}


def test_result_event_excludes_empty_dict_but_keeps_empty_list(chat_client, session):
    """F2: from_analysis_state in supervisor.py unconditionally puts defaults such as
    id_mapping_result: {} into state (when that subgraph never ran). The frontend cannot
    tell this apart from "did not run", so it must be excluded just like None. But an
    empty list for significant_metabolites is unaffected and must be kept -- this pins
    the asymmetric "drop empty dict, keep empty list" semantics across three cases at once."""
    tid = _prepare(session)

    class MixedEmptyAgent:
        def invoke(self, payload, config=None):
            return {
                "messages": [AIMessage(content="分析完成")],
                "intent": "analysis",
                "analysis_result": {"r_code": "t.test(x, y)", "success": True},
                "id_mapping_result": {},
                "significant_metabolites": [],
            }

    chat_client.app.state.main_agent = MixedEmptyAgent()
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    events = _parse_sse(res.text)
    result_events = [d for name, d in events if name == "result"]
    assert len(result_events) == 1
    data = result_events[0]["data"]
    assert set(data.keys()) == {"analysis_result", "significant_metabolites"}
    assert data["significant_metabolites"] == []


def test_result_payload_sanitizes_numpy_and_path_for_sse_and_db(chat_client, session):
    """Ruling 2: analysis_result may contain numpy types or Path objects, neither of which
    json.dumps can serialize directly or which can go straight into JSONB. The SSE result
    event and the blocks stored in ChatMessage.content must share the same sanitized data;
    neither side may crash with TypeError or store the unsanitized raw objects."""
    tid = _prepare(session)

    class NumpyPayloadAgent:
        def invoke(self, payload, config=None):
            return {
                "messages": [AIMessage(content="分析完成")],
                "intent": "analysis",
                "analysis_result": {
                    # Neither np.int64 nor Path is natively json-serializable
                    # (np.float64 is a float subclass and does not trigger TypeError,
                    # so it is deliberately not used here, to avoid a coincidental pass).
                    "n_samples": np.int64(42),
                    "output_path": Path("uploads/output/analysis/x.csv"),
                },
            }

    chat_client.app.state.main_agent = NumpyPayloadAgent()
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    assert res.status_code == 200

    events = _parse_sse(res.text)
    result_events = [d for name, d in events if name == "result"]
    assert len(result_events) == 1
    ar = result_events[0]["data"]["analysis_result"]
    # F4: use _json_fallback (numpy scalars go through .item()) instead of str();
    # np.int64(42) must become the native number 42, not the string "42" -- otherwise
    # the frontend cannot sort/format this value.
    assert ar["n_samples"] == 42
    assert ar["output_path"] == "uploads/output/analysis/x.csv"

    msg = session.exec(
        select(ChatMessage)
        .where(ChatMessage.thread_id == tid)
        .where(ChatMessage.role == "assistant")
    ).one()
    by_type = {b["type"]: b for b in msg.content}
    db_analysis_result = by_type["result"]["data"]["analysis_result"]
    assert db_analysis_result["n_samples"] == 42
    assert db_analysis_result["output_path"] == "uploads/output/analysis/x.csv"


def test_unserializable_structured_payload_is_dropped_not_treated_as_crash(chat_client, session):
    """F4: if analysis_result contains a structure json cannot serialize at all (e.g. the
    "numpy scalar as dict key" common with df.to_dict()), the whole SSE stream must not
    pretend the agent crashed. The text reply must still be delivered, with only the
    structured fields dropped this time; no error event unrelated to what actually
    happened may be emitted (the analysis succeeded, only the format was abnormal)."""
    tid = _prepare(session)

    class BadKeyAgent:
        def invoke(self, payload, config=None):
            return {
                "messages": [AIMessage(content="分析完成，但結果格式異常")],
                "intent": "analysis",
                # The dict key is np.int64: not even default= can rescue json.dumps,
                # because that rule applies to values, not keys.
                "analysis_result": {np.int64(1): "value"},
            }

    chat_client.app.state.main_agent = BadKeyAgent()
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    assert res.status_code == 200

    events = _parse_sse(res.text)
    names = [name for name, _ in events]
    assert "error" not in names
    assert "result" not in names
    text_events = [d for name, d in events if name == "text"]
    assert text_events[0]["content"] == "分析完成，但結果格式異常"
    assert "saved" in names


def test_db_write_failure_emits_error_event_not_saved(session):
    """Ruling 3/F7: a failure to write the assistant message to the database must not be
    swallowed silently -- an error event must be emitted, and saved must not be emitted
    as well (otherwise the frontend gets a false success signal).

    F7: the proxy raises on commit() (not add()) -- real failures (psycopg2 adapt errors,
    constraint violations, dropped connections) are raised at commit(), not at add().
    This way session.rollback() is really called in a "this transaction failed" situation;
    if someone ever removes session.rollback() from the except branch, the assertion
    below that "no assistant row was quietly left behind" catches it (the pending object
    would really be written on the next autoflush).
    """
    from api.database import get_session
    from fastapi.testclient import TestClient
    from main import create_app

    tid = _prepare(session)

    class FailingOnAssistantCommit:
        """Wraps the session and deliberately fails only when about to commit a ChatMessage
        with role="assistant"; all other commits (user message, title update) pass
        normally, without relying on a fragile implementation detail such as call counts."""

        def __init__(self, real):
            object.__setattr__(self, "_real", real)

        def __getattr__(self, name):
            return getattr(object.__getattribute__(self, "_real"), name)

        def commit(self):
            if any(isinstance(o, ChatMessage) and o.role == "assistant"
                   for o in self._real.new):
                raise RuntimeError("模擬 DB 寫入失敗")
            return self._real.commit()

    failing_session = FailingOnAssistantCommit(session)

    app = create_app()
    app.dependency_overrides[get_session] = lambda: failing_session
    with TestClient(app) as c:
        c.app.state.main_agent = FakeAgent()
        res = c.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    app.dependency_overrides.clear()

    assert res.status_code == 200
    events = _parse_sse(res.text)
    assert not any(name == "saved" for name, _ in events)
    error_events = [d for name, d in events if name == "error"]
    assert len(error_events) == 1
    assert "回覆儲存失敗" in error_events[0]["content"]

    # The session must remain usable after the failed commit and rollback: the existing
    # user message is still there, and no assistant row was accidentally left behind.
    rows = session.exec(
        select(ChatMessage).where(ChatMessage.thread_id == tid)
    ).all()
    assert any(r.role == "user" for r in rows)
    assert not any(r.role == "assistant" for r in rows)


def test_agent_crash_after_status_persists_trace_but_no_saved_event(chat_client, session):
    """F1: the agent crashes after emitting two status events (an R script exiting non-zero,
    an OpenAI timeout, a subgraph crash are everyday events for this system, not
    theoretical edge cases). The DB must still keep this "trace-only" record (the crash
    trail is data needed for debugging), but saved must never be emitted -- saved means
    only that a complete answer has been stored."""
    tid = _prepare(session)

    class CrashAfterStatusAgent:
        def invoke(self, payload, config=None):
            writer = config["configurable"]["writer"]
            writer({"status": "Parameter extraction complete, statistical analysis in progress."})
            writer({"status": "Summary complete! Ready to download."})
            raise RuntimeError("R script exited with code 1")

    chat_client.app.state.main_agent = CrashAfterStatusAgent()
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    assert res.status_code == 200

    events = _parse_sse(res.text)
    names = [name for name, _ in events]
    assert "saved" not in names
    assert "error" in names

    msg = session.exec(
        select(ChatMessage)
        .where(ChatMessage.thread_id == tid)
        .where(ChatMessage.role == "assistant")
    ).one()
    blocks = msg.content
    assert len(blocks) == 1
    assert blocks[0]["type"] == "trace"
    assert len(blocks[0]["steps"]) == 2


def test_text_event_content_field_shape(chat_client, session):
    """F6: text is an event the existing frontend consumes (useChatStream.ts reads
    text.content). This task did not change its logic, but pins it with an explicit shape
    test, treated the same as status/zip_ready."""
    tid = _prepare(session)
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    text_events = [d for name, d in _parse_sse(res.text) if name == "text"]
    assert len(text_events) == 1
    assert text_events[0] == {"content": "分析完成"}


def test_zip_ready_event_folder_name_field_shape(chat_client, session):
    """F6: zip_ready is an event the existing frontend consumes (useChatStream.ts reads
    zip_ready.folder_name); its shape is pinned together with text/status."""
    tid = _prepare(session)
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    zip_events = [d for name, d in _parse_sse(res.text) if name == "zip_ready"]
    assert len(zip_events) == 1
    assert zip_events[0] == {"folder_name": "uploads/output/analysis/2026-01-01"}


def test_result_block_persists_output_folder(chat_client, session):
    """Task 15: the ResultCard "files" tab needs the artifacts folder, but when history is
    reloaded the SSE zip_ready (which only happens during live streaming) no longer exists,
    so folder must be persisted into the DB with the result block, for reading history at
    any later time."""
    tid = _prepare(session)
    chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})

    msg = session.exec(
        select(ChatMessage)
        .where(ChatMessage.thread_id == tid)
        .where(ChatMessage.role == "assistant")
    ).one()
    result_block = next(b for b in msg.content if b["type"] == "result")
    assert result_block["folder"] == "uploads/output/analysis/2026-01-01"


def _mkdir_output(intent: str, date: str) -> Path:
    d = UPLOAD_ROOT / "output" / intent / date
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_verified_output_folder_corrects_wrong_reported_path(chat_client, session):
    """F1: `analysis_graph.py:424` has a copy-paste bug in the frozen zone -- the report is
    written under `analysis/` but `literature/` is reported. When the reported path does
    not exist and the date segment matches exactly one real folder under
    uploads/output/*/<date>, that folder must replace the wrong reported value (reflected
    in both zip_ready and the persisted result block folder, which are the same variable)."""
    tid = _prepare(session)
    date = "2026-02-02"
    real_dir = _mkdir_output("analysis", date)

    class WrongFolderAgent:
        def invoke(self, payload, config=None):
            writer = config["configurable"]["writer"]
            writer({"status": "Summary complete! Ready to download.",
                     "output_file_path": f"uploads/output/literature/{date}"})
            return {
                "messages": [AIMessage(content="分析完成")],
                "intent": "analysis",
                "analysis_result": {"r_code": "t.test(x, y)", "success": True},
            }

    try:
        chat_client.app.state.main_agent = WrongFolderAgent()
        res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
        events = _parse_sse(res.text)
        zip_events = [d for name, d in events if name == "zip_ready"]
        assert len(zip_events) == 1
        assert zip_events[0]["folder_name"] == f"uploads/output/analysis/{date}"

        msg = session.exec(
            select(ChatMessage)
            .where(ChatMessage.thread_id == tid)
            .where(ChatMessage.role == "assistant")
        ).one()
        result_block = next(b for b in msg.content if b["type"] == "result")
        assert result_block["folder"] == f"uploads/output/analysis/{date}"
    finally:
        shutil.rmtree(real_dir, ignore_errors=True)


def test_verified_output_folder_keeps_existing_reported_path(chat_client, session):
    """When the reported path itself exists, use it as-is -- adding validation is no reason
    to needlessly "guess" a seemingly better answer."""
    tid = _prepare(session)
    date = "2026-02-03"
    real_dir = _mkdir_output("analysis", date)

    class CorrectFolderAgent:
        def invoke(self, payload, config=None):
            writer = config["configurable"]["writer"]
            writer({"status": "Summary complete! Ready to download.",
                     "output_file_path": f"uploads/output/analysis/{date}"})
            return {"messages": [AIMessage(content="分析完成")], "intent": "analysis"}

    try:
        chat_client.app.state.main_agent = CorrectFolderAgent()
        res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
        zip_events = [d for name, d in _parse_sse(res.text) if name == "zip_ready"]
        assert len(zip_events) == 1
        assert zip_events[0]["folder_name"] == f"uploads/output/analysis/{date}"
    finally:
        shutil.rmtree(real_dir, ignore_errors=True)


def test_verified_output_folder_keeps_original_when_ambiguous(chat_client, session):
    """When the date segment matches real folders under several subdirectories, do not
    guess -- keep the original value, so the downstream /api/artifacts 404 message still
    appears, instead of silently substituting another folder that may be just as wrong."""
    tid = _prepare(session)
    date = "2026-02-04"
    dir_a = _mkdir_output("analysis", date)
    dir_b = _mkdir_output("zip", date)

    class AmbiguousFolderAgent:
        def invoke(self, payload, config=None):
            writer = config["configurable"]["writer"]
            writer({"status": "Summary complete! Ready to download.",
                     "output_file_path": f"uploads/output/literature/{date}"})
            return {"messages": [AIMessage(content="分析完成")], "intent": "analysis"}

    try:
        chat_client.app.state.main_agent = AmbiguousFolderAgent()
        res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
        zip_events = [d for name, d in _parse_sse(res.text) if name == "zip_ready"]
        assert len(zip_events) == 1
        assert zip_events[0]["folder_name"] == f"uploads/output/literature/{date}"
    finally:
        shutil.rmtree(dir_a, ignore_errors=True)
        shutil.rmtree(dir_b, ignore_errors=True)


def test_verified_output_folder_uses_result_files_when_date_glob_finds_nothing(chat_client, session):
    """I2 (found in a scoped re-review): on the success path the real folder name is
    `{csv file name}_{%Y%m%d_%H%M%S}` (`use_tool/code.py`, frozen zone), which does not
    match the reported date in `%Y-%m-%d-%H-%M-%S` format -- the date glob gets 0 hits in
    this situation, so the old F1 fix did nothing for the success path.
    `analysis_result["result_files"]` is a more reliable signal; this verifies that it
    takes precedence over the date glob and handles `result_files` with a `/backend/`
    prefix (the format caused by `use_tool/code.py` computing relative paths from the
    monorepo root)."""
    tid = _prepare(session)
    real_dir = UPLOAD_ROOT / "output" / "analysis" / "peaktable_20260803_204100"
    real_dir.mkdir(parents=True, exist_ok=True)
    (real_dir / "report.md").write_text("# report", encoding="utf-8")

    class ResultFilesAgent:
        def invoke(self, payload, config=None):
            writer = config["configurable"]["writer"]
            writer({"status": "Summary complete! Ready to download.",
                     "output_file_path": "uploads/output/literature/2026-08-03-20-41-00"})
            return {
                "messages": [AIMessage(content="分析完成")],
                "intent": "analysis",
                "analysis_result": {
                    "r_code": "t.test(x, y)",
                    "success": True,
                    "result_files": [
                        "/backend/uploads/output/analysis/peaktable_20260803_204100/report.md",
                    ],
                },
            }

    try:
        chat_client.app.state.main_agent = ResultFilesAgent()
        res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
        assert res.status_code == 200

        msg = session.exec(
            select(ChatMessage)
            .where(ChatMessage.thread_id == tid)
            .where(ChatMessage.role == "assistant")
        ).one()
        result_block = next(b for b in msg.content if b["type"] == "result")
        assert result_block["folder"] == "uploads/output/analysis/peaktable_20260803_204100"
    finally:
        shutil.rmtree(real_dir, ignore_errors=True)


def test_zip_ready_uses_the_result_files_corrected_folder(chat_client, session):
    """Seen in practice (2026-08-12): pressing the ZIP download button right after an
    analysis finished always gave 404; the same button only worked after a page refresh.

    The test above only pinned the folder persisted into the DB, not zip_ready -- and
    zip_ready used to be sent at the moment of the `output_file_path` status event, when
    `analysis_result` was not yet in the queue, leaving `_verified_output_folder` with only
    layers 1 and 3: the reported path did not exist, and the date glob got 0 hits because
    the two time formats do not match, so the wrong original value was sent anyway.
    The success path therefore **always** sent a literature path that never existed, and
    `/api/uploads/download-zip` returned 404 with the "backend cannot find the physical
    folder" detail.

    This was the default outcome of the success path, not an edge case: users hit it just
    as developers do, and the 404 message points at a nonexistent folder, which looks as if
    the files were never produced. The fix delays zip_ready until `result_files` is in hand
    and the folder has received its final correction.
    """
    tid = _prepare(session)
    real_dir = UPLOAD_ROOT / "output" / "analysis" / "peaktable_20260812_134032"
    real_dir.mkdir(parents=True, exist_ok=True)
    (real_dir / "report.md").write_text("# report", encoding="utf-8")

    class ResultFilesAgent:
        def invoke(self, payload, config=None):
            writer = config["configurable"]["writer"]
            writer({"status": "Summary complete! Ready to download.",
                     "output_file_path": "uploads/output/literature/2026-08-12-13-40-23"})
            return {
                "messages": [AIMessage(content="分析完成")],
                "intent": "analysis",
                "analysis_result": {
                    "r_code": "t.test(x, y)",
                    "success": True,
                    "result_files": [
                        "/backend/uploads/output/analysis/peaktable_20260812_134032/report.md",
                    ],
                },
            }

    try:
        chat_client.app.state.main_agent = ResultFilesAgent()
        res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
        zip_events = [d for name, d in _parse_sse(res.text) if name == "zip_ready"]
        assert len(zip_events) == 1
        assert zip_events[0]["folder_name"] == (
            "uploads/output/analysis/peaktable_20260812_134032")
    finally:
        shutil.rmtree(real_dir, ignore_errors=True)


def test_zip_ready_precedes_saved(chat_client, session):
    """After delaying zip_ready, it must still be sent before `saved`.

    `saved` is the stream's closing signal; the frontend `useChatStream` treats the turn as
    finished when it reads it. If zip_ready came after it, it would still be in the same
    response, but "end of stream" would no longer be the last event, making any consumer
    that relies on that order fragile. Pinned separately, because every test above only
    counts zip_events without looking at its position relative to other events."""
    tid = _prepare(session)
    res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
    names = [name for name, _ in _parse_sse(res.text)]
    assert "zip_ready" in names and "saved" in names
    assert names.index("zip_ready") < names.index("saved")


def _seed_answered_exchange(session, tid: str, message: str, answered_at: datetime) -> None:
    """Put an "already answered" [user, assistant] pair into the thread.

    The assistant row is deliberately 5 seconds later than the user row: the early-exit
    check does `order_by(created_at.desc()).limit(2)` and then checks
    `[0].role == "assistant"`. If both rows shared the same created_at, the database would
    decide which comes first (undefined) -- and the test would pass or fail by ordering
    coincidence rather than because of the logic under test.
    """
    session.add(ChatMessage(
        thread_id=tid, role="user",
        content=[{"type": "text", "text": message}],
        created_at=answered_at - timedelta(seconds=5),
    ))
    session.add(ChatMessage(
        thread_id=tid, role="assistant",
        content=[{"type": "text", "text": "共 0 篇"}],
        created_at=answered_at,
    ))
    session.commit()


def test_identical_message_long_after_answer_runs_the_agent_again(chat_client, session):
    """Seen in practice (2026-08-04): literature search first returned 0 papers because
    `NCBI_KEY` was an empty string, and when the physician asked the exact same question
    again in the same thread, a new answer never came.

    The cause: the "duplicate request early exit" compared only content, with no time
    condition at all, so as long as the last exchange happened to be the same question,
    asking again at any later time was judged a duplicate and the old 0-paper answer was
    returned directly. Its comment says "the previous request with the same content has
    just completed" -- this test makes "just" actually hold.

    The consequence was that once a user's first run failed, it could never be re-run.
    """
    tid = _prepare(session)
    _seed_answered_exchange(session, tid, "搜尋乳酸與腫瘤微環境",
                            datetime.now(timezone.utc) - timedelta(minutes=10))

    res = chat_client.post(f"/api/chat/{tid}", json={"message": "搜尋乳酸與腫瘤微環境"})

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    names = [name for name, _ in _parse_sse(res.text)]
    assert "saved" in names


def test_identical_message_immediately_after_answer_still_early_returns(chat_client, session):
    """The early exit itself must stay: it guards against "the same message being sent again
    right after the answer landed" (frontend replay, browser restoring a POST). This verifies
    that behaviour inside the window was not changed by the fix above; otherwise the fix
    would merely have removed the guard entirely.
    """
    tid = _prepare(session)
    _seed_answered_exchange(session, tid, "搜尋乳酸與腫瘤微環境",
                            datetime.now(timezone.utc))

    res = chat_client.post(f"/api/chat/{tid}", json={"message": "搜尋乳酸與腫瘤微環境"})

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    assert res.json()["status"] == "success"
    # The agent did not run: the thread still has only the original two rows, no new user/assistant.
    rows = session.exec(select(ChatMessage).where(ChatMessage.thread_id == tid)).all()
    assert len(rows) == 2


def test_verified_output_folder_falls_back_to_date_glob_when_result_files_invalid(chat_client, session):
    """When `result_files` points to an out-of-bounds or nonexistent path, do not give up
    entirely -- fall back to the date glob, a weaker but still valid strategy (the date glob
    is deliberately given a unique hit here), proving the strategy order is correct and
    every layer has a fallback."""
    tid = _prepare(session)
    date = "2026-08-05"
    real_dir = _mkdir_output("analysis", date)

    class BadResultFilesAgent:
        def invoke(self, payload, config=None):
            writer = config["configurable"]["writer"]
            writer({"status": "Summary complete! Ready to download.",
                     "output_file_path": f"uploads/output/literature/{date}"})
            return {
                "messages": [AIMessage(content="分析完成")],
                "intent": "analysis",
                "analysis_result": {
                    # Out-of-bounds path: resolve_uploads_path raises ValueError, which
                    # must be caught and fall back to the date glob, not interrupt SSE.
                    "result_files": ["/etc/passwd"],
                },
            }

    try:
        chat_client.app.state.main_agent = BadResultFilesAgent()
        res = chat_client.post(f"/api/chat/{tid}", json={"message": "分析這個"})
        assert res.status_code == 200

        msg = session.exec(
            select(ChatMessage)
            .where(ChatMessage.thread_id == tid)
            .where(ChatMessage.role == "assistant")
        ).one()
        result_block = next(b for b in msg.content if b["type"] == "result")
        assert result_block["folder"] == f"uploads/output/analysis/{date}"
    finally:
        shutil.rmtree(real_dir, ignore_errors=True)
