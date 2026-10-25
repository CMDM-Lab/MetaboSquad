import os
import pytest
from dotenv import load_dotenv

load_dotenv()

TEST_PG_URL = os.environ.get("TEST_PG_URL")
if not TEST_PG_URL:
    pytest.skip("TEST_PG_URL 未設定，跳過需要資料庫的測試", allow_module_level=True)

# Must be set before importing app, because database.py creates the engine at import time
os.environ["PG_URL"] = TEST_PG_URL
os.environ["SKIP_AGENT_INIT"] = "1"

from sqlalchemy import text  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

test_engine = create_engine(TEST_PG_URL)


# Contract: a test file must import the model classes it uses at module top level
# (e.g. `from api.routers.chat import Chat`); do not hide the import inside a function.
# Reason: SQLModel.metadata only contains models that have already been imported,
# and both create_all and truncate below depend on metadata being complete. pytest
# imports every test module during collection, so as long as each test file imports
# its models at module top level, metadata is guaranteed complete when the fixture runs.
@pytest.fixture(name="session")
def session_fixture():
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session
    # Clear after every test, to avoid unique-constraint conflicts (e.g. Chat.thread_id)
    # accumulating across tests and flakiness caused by test order.
    # TRUNCATE ... CASCADE handles all SQLModel-managed tables and their foreign-key
    # order in one go; LangGraph's own checkpoints tables are not in metadata and are
    # unaffected.
    # Truncate rather than transaction + rollback: API endpoints call session.commit()
    # themselves, so a rollback approach would need an extra SAVEPOINT/nested
    # transaction to stop the API's commit from ending the outer transaction early.
    # That is more complex and more prone to subtle bugs; truncate keeps the API's
    # commit semantics real.
    tables = SQLModel.metadata.sorted_tables
    if tables:
        names = ", ".join(f'"{t.name}"' for t in tables)
        with test_engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {names} CASCADE"))


@pytest.fixture(name="client")
def client_fixture(session):
    """`with TestClient(app)` triggers the lifespan (both startup and shutdown run),
    but the SKIP_AGENT_INIT branch in `main.py` short-circuits LangGraph initialization,
    so no real OpenAI key or Postgres checkpointer is needed here.
    """
    from main import create_app
    from api.database import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
