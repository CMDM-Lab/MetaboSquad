# main.py
from fastapi import FastAPI
from typing import Dict
import os
import sys
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from api.routers import artifacts, chat, uploads, tool
from contextlib import asynccontextmanager
from langgraph.store.postgres import PostgresStore
from langgraph.checkpoint.postgres import PostgresSaver
from api.database import create_db_and_tables, run_migrations
from dotenv import load_dotenv

from src.graph_agent.supervisor import build_main_graph


def _ensure_interpreter_bin_on_path() -> None:
    """Add the directory of the running interpreter to PATH.

    The graph calls an external CLI via `subprocess.run(["mummichog", ...])`
    (`use_tool/pathway_analysis.py`), and that executable is pip-installed into `venv/bin/`.
    The problem is that the production start command names the interpreter directly:

        venv/bin/python -m uvicorn main:app ...

    This does **not** activate the venv, so `venv/bin` is not on PATH. The result: the package is
    installed and `venv/bin/mummichog` exists, yet subprocess still raises FileNotFoundError and the
    report only says that the 'mummichog' command was not found on the system -- which looks like it is not installed.

    Do not use `.resolve()`: `venv/bin/python` is a symlink to `/usr/bin/python3.x`, and resolving it
    yields `/usr/bin` (already on PATH, so this would do nothing).
    Console scripts are installed in the directory where the symlink lives.

    Guarded by `tests/test_venv_bin_on_path.py`.
    """
    bin_dir = str(Path(sys.executable).parent)
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if bin_dir and bin_dir not in parts:
        os.environ["PATH"] = os.pathsep.join([bin_dir, *parts])


# Applied at import time, not in lifespan: tests and every path that imports main must see the same effect.
_ensure_interpreter_bin_on_path()


def _parse_origins(raw: str) -> list[str]:
    """Turn a comma-separated string into a list of origins, stripping whitespace and dropping empty items."""
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    db_url = os.environ["PG_URL"]

    # On startup, make sure the SQLModel tables exist
    create_db_and_tables()
    run_migrations()

    if os.environ.get("SKIP_AGENT_INIT") == "1":
        app.state.main_agent = None
        print("⚠️  SKIP_AGENT_INIT=1，跳過 LangGraph 初始化（測試模式）")
        yield
        return

    with PostgresStore.from_conn_string(db_url) as store, \
         PostgresSaver.from_conn_string(db_url) as checkpointer:

        # Initialise LangGraph's own internal system tables (if they do not exist)
        store.setup()
        checkpointer.setup()

        # Build the agent graph instance
        main_agent = build_main_graph(store, checkpointer)

        # Attach to app.state for use by other routers
        app.state.main_agent = main_agent
        app.state.store = store
        app.state.checkpointer = checkpointer

        print("✅ Database tables initialized and connected via Sync Context Manager.")

        yield

        print("🔄 FastAPI is shutting down... Closing database connections.")
        # On leaving the with block, the store and checkpointer connections are released automatically

def create_app() -> FastAPI:
    # Create the app and bind the lifespan defined above
    app = FastAPI(
        title="Metabolism Analysis API",
        version="1.0.0",
        lifespan=lifespan
    )
    
    default_origins = "http://localhost,http://localhost:8080,http://localhost:3000"
    # `or` rather than get(..., default): CORS_ORIGINS="" (set but empty) must
    # also fall back, otherwise allow_origins=[] silently blocks every frontend origin with no log.
    origins = _parse_origins(os.environ.get("CORS_ORIGINS") or default_origins)
    if not origins:
        # e.g. CORS_ORIGINS="," or " , ": a value is set, but every item is empty after split,
        # which the `or` above does not catch. allow_origins=[] silently blocks every frontend
        # origin, so fall back and log it -- "nothing connects and there is no clue why" at deploy
        # time is far worse than rejecting one bad setting.
        print("⚠️ CORS_ORIGINS 解析後為空，回退到預設 localhost 清單")
        origins = _parse_origins(default_origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    # Make sure the upload and download directories exist so StaticFiles does not fail on a missing folder
    UPLOAD_DIR = os.path.abspath("uploads")
    ZIP_DIR = os.path.abspath(os.path.join("uploads", "output", "zip"))
    
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(ZIP_DIR, exist_ok=True) # Make sure the zip folder always exists
    
    # Mount static files (so URLs starting with /uploads/ map directly to the physical uploads folder)
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
    
    # Register all routers
    app.include_router(chat.router)
    app.include_router(uploads.router)
    app.include_router(tool.router)
    app.include_router(artifacts.router)

    return app

# Initialise the application
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

