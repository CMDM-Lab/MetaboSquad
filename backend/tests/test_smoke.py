from sqlalchemy import text

# Per the contract, import the models used at module top level so SQLModel.metadata is complete
# (see the session_fixture comment in conftest.py).
from api.routers.chat import Chat


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_session_fixture_connects_to_test_database(session):
    """Confirm the session fixture connects to a test database (name ends in `_test`), not the production database.
    If the order of environment-variable setup ever breaks, tests would silently write to
    the production database instead of failing, so this asserts on current_database() directly.
    """
    db_name = session.execute(text("SELECT current_database()")).scalar_one()
    assert db_name.endswith("_test"), db_name


def test_dependency_override_is_used_by_api(client, session):
    """Confirm the client fixture's dependency override really takes effect.

    Note: conftest sets os.environ["PG_URL"] to TEST_PG_URL before importing
    `api.database`, so even without the override, api.database.engine connects to the
    same physical test database -- "session.add + commit" cannot detect whether the
    override works, because after commit any connection to that database can see it.

    The method that can detect it: add without commit. If the override works, list_chat
    uses "the same session object" (the same transaction), and SQLAlchemy's autoflush
    makes the uncommitted Chat visible to the query; if it does not, the API uses a
    brand-new session/connection from api.database.engine, which under transaction
    isolation cannot see uncommitted data, and this test fails -- exactly the detecting
    power we want.
    """
    chat = Chat(thread_id="smoke-test-thread", title="smoke test chat")
    session.add(chat)

    res = client.get("/api/chat/")
    assert res.status_code == 200
    body = res.json()
    thread_ids = [c["thread_id"] for c in body["chats"]]
    assert "smoke-test-thread" in thread_ids
