"""A chat title should show its topic at a glance.

Every chat in the sidebar used to show the same "new conversation" placeholder, carrying
no information. Investigation found that **the title was never updated**, due to a
sentinel mismatch bug:

    chat.py  add_chat writes          title=<"new conversation" (Chinese)>
    chat.py  Chat model default       title=<"new chat" (Chinese)>
    chat.py  continue_chat condition  if chat_db.title == <"new chat" (Chinese)>

The two strings differ, so the "use the first message as the title" code never ran.
-> Unified into a single constant DEFAULT_CHAT_TITLE, so the two sides can no longer drift apart.
"""

import pytest

from api.routers.chat import DEFAULT_CHAT_TITLE, Chat


def test_add_chat_and_rename_condition_use_the_same_sentinel(client, session):
    """A new chat's title must equal the value `continue_chat` uses to decide "not yet named".

    This was the root of the whole bug: two places each hard-coded a Chinese string, and
    they differed. Assert that they are the same constant, not that "both equal some
    literal" -- the latter would still pass if the two sides drifted again.
    """
    res = client.post("/api/chat/")
    assert res.status_code == 200
    assert res.json()["title"] == DEFAULT_CHAT_TITLE

    from sqlmodel import select
    chat = session.exec(
        select(Chat).where(Chat.thread_id == res.json()["thread_id"])).one()
    assert chat.title == DEFAULT_CHAT_TITLE


def test_first_message_becomes_the_title(spy_chat_client, session):
    """The first message becomes the title. Before the fix this never worked because of the sentinel mismatch."""
    tid = spy_chat_client.post("/api/chat/").json()["thread_id"]

    spy_chat_client.post(f"/api/chat/{tid}",
                         json={"message": "請幫我查 citric acid 的 PubChem CID"})

    from sqlmodel import select
    chat = session.exec(select(Chat).where(Chat.thread_id == tid)).one()
    assert chat.title != DEFAULT_CHAT_TITLE
    assert "citric acid" in chat.title


def test_first_message_does_not_overwrite_a_renamed_title(spy_chat_client, session):
    """A title the user has changed must not be overwritten by the first message.

    `continue_chat` only renames while the title is still the default.
    """
    tid = spy_chat_client.post("/api/chat/").json()["thread_id"]
    spy_chat_client.patch(f"/api/chat/{tid}", json={"title": "分析 LC-MS 資料"})

    spy_chat_client.post(f"/api/chat/{tid}",
                         json={"message": "請找出兩組之間顯著差異的代謝物"})

    from sqlmodel import select
    chat = session.exec(select(Chat).where(Chat.thread_id == tid)).one()
    assert chat.title == "分析 LC-MS 資料"


@pytest.fixture(name="spy_chat_client")
def spy_chat_client_fixture(session):
    """A client that really goes through POST /api/chat/{tid}, but with a fake agent."""
    from fastapi.testclient import TestClient
    from langchain_core.messages import AIMessage

    from api.database import get_session
    from main import create_app

    class FakeAgent:
        def invoke(self, payload, config=None):
            return {"messages": [AIMessage(content="ok")]}

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        c.app.state.main_agent = FakeAgent()
        yield c
    app.dependency_overrides.clear()
