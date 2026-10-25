"""`files` state channel: uploaded files must actually reach the graph's state.

Measured on 2026-08-04: the analysis_lcms and plot_review cases had **never once** run
successfully through the web UI. The cause: `chat.py` invoked the agent with only
`{"messages": [...]}`, so the `files` channel was never filled. And
`_correct_misclassification` in `supervisor.py` does:

    # correction case 0: intent is plot review or data analysis but no file given -> force direct
    if intent in ["plot_review", "analysis"] and not files:
        task["intent"] = "direct"

So the LLM got the intent right, and the correction logic then changed it to direct
(plain chat). The user saw a "please wait, analysing now" reply and then nothing
happened -- because that turn had already ended, and the next turn never comes by itself.

This is the same class of problem as review_result: LangGraph does not complain about a
channel that is declared but never filled; behaviour just silently differs.
"""

import pytest
from langchain_core.messages import AIMessage

from api.routers.chat import Chat


class SpyAgent:
    """Record the payload invoke receives, and do nothing else."""

    def __init__(self):
        self.payload = None

    def invoke(self, payload, config=None):
        self.payload = payload
        return {"messages": [AIMessage(content="ok")]}


@pytest.fixture(name="spy_client")
def spy_client_fixture(session):
    from fastapi.testclient import TestClient

    from api.database import get_session
    from main import create_app

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        c.app.state.main_agent = SpyAgent()
        yield c
    app.dependency_overrides.clear()


def _prepare(session) -> str:
    session.add(Chat(thread_id="th-files", title="新聊天"))
    session.commit()
    return "th-files"


def test_no_upload_still_sends_empty_files_list(spy_client, session):
    """With no uploaded file, `files` must be an empty list, not a missing key --
    `state.get("files", [])` behaves the same for both, but explicitly sending an empty
    list makes "no files this turn" a deliberate signal rather than a forgotten field."""
    tid = _prepare(session)
    spy_client.post(f"/api/chat/{tid}", json={"message": "citric acid 的 CID？"})
    assert spy_client.app.state.main_agent.payload["files"] == []


def test_uploaded_csv_reaches_files_channel_in_graph_readable_form(spy_client, session):
    """The CSV path format is `../../uploads/...`, not the intuitive `uploads/...`.

    The cause is in the frozen zone: `extract_schema_and_config` in `use_tool/code.py`
    builds paths from `BASE_DIR = Path(__file__).resolve().parent.parent` (=
    `backend/src/graph_agent`), which has no uploads underneath. Of four formats tried,
    only `../../uploads/...` finds the file (see
    `test_csv_prefix_actually_resolves_to_the_real_file`).
    """
    tid = _prepare(session)
    spy_client.post(
        f"/api/chat/{tid}",
        json={"message": "請分析", "file_path": "/uploads/csv/lcms_table.csv"}
    )
    assert spy_client.app.state.main_agent.payload["files"] == [
        "../../uploads/csv/lcms_table.csv"
    ]


def test_uploaded_image_reaches_files_channel_with_cwd_relative_path(spy_client, session):
    """Image files use a **different** format from CSV: `uploads/image/...`.

    `_load_image_as_base64` in `plot_graph.py` uses a bare `open(path)`, i.e.
    CWD-relative, and uvicorn's CWD is `backend/`. No single `files` value can satisfy
    both subgraphs, so the file extension decides the format.
    """
    tid = _prepare(session)
    spy_client.post(
        f"/api/chat/{tid}",
        json={"message": "審查這張圖",
              "file_path": "/uploads/image/benchmark_semantic_pca_01.png"}
    )
    assert spy_client.app.state.main_agent.payload["files"] == [
        "uploads/image/benchmark_semantic_pca_01.png"
    ]


def test_no_system_hint_is_appended_to_the_user_message(spy_client, session):
    """Paths may only travel via `files`; no text hint may be appended to the message body.

    `chat.py` used to append a system hint to the message saying the user uploaded a
    file at `csv/lcms_table.csv`. That was the only way to pass it along back when the
    `files` channel was never filled. Now that `files` is passed correctly, the hint is
    redundant -- and it shows up in two places physicians can see:

    1. the physician's **own message bubble** in the chat (the text is stored in ChatMessage.content)
    2. the plot_review report (the "original research question" field is printed verbatim)

    The graph already has its own mechanism for adding paths (`input_verifier_node` in
    `supervisor.py` appends a line with the uploaded file paths when the message does not
    mention the file), so after removing it the LLM still knows where the file is.
    """
    tid = _prepare(session)
    spy_client.post(
        f"/api/chat/{tid}",
        json={"message": "請分析", "file_path": "/uploads/csv/lcms_table.csv"}
    )

    sent = spy_client.app.state.main_agent.payload["messages"][0]["content"]
    text = next(b["text"] for b in sent if b["type"] == "text")
    assert text == "請分析", f"訊息本文被加料了：{text!r}"
    assert "系統提示" not in text

    # What is stored in the DB must be clean too -- the chat bubbles are read back from here.
    from sqlmodel import select

    from api.routers.chat import ChatMessage

    user_msg = session.exec(
        select(ChatMessage).where(ChatMessage.thread_id == tid)
        .where(ChatMessage.role == "user")
    ).one()
    assert "系統提示" not in str(user_msg.content)


# --- The two below are tripwires: they pin "why" the two formats above are correct ---

def test_csv_prefix_actually_resolves_to_the_real_file():
    """The `../../uploads/` prefix looks like a typo; it compensates for a bug in the frozen zone.

    If someone ever fixes `BASE_DIR` in `extract_schema_and_config`, this test turns red
    as a reminder to change the prefix in `chat.py` back to `uploads/` -- otherwise it
    breaks the other way.
    """
    from src.graph_agent.use_tool.code import extract_schema_and_config

    ok = extract_schema_and_config("../../uploads/csv/lcms_table.csv",
                                   "Label", False, False)
    assert ok.get("group_count") == 2, (
        "凍結區的 extract_schema_and_config 路徑解析行為變了，"
        "請一併更新 chat.py 的 _graph_file_path"
    )

    # Control: the intuitive format is still broken. This line says "the prefix is not
    # decoration" -- if it ever starts working, BASE_DIR has been fixed and the
    # compensation above should be removed.
    naive = extract_schema_and_config("uploads/csv/lcms_table.csv",
                                      "Label", False, False)
    assert naive.get("group_count") is None


def test_image_path_is_readable_from_process_cwd():
    """The image path relies on uvicorn's CWD being `backend/`."""
    from pathlib import Path

    assert Path("uploads/image/benchmark_semantic_pca_01.png").is_file()
