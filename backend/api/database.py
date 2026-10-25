# database.py
from sqlmodel import Session, create_engine, SQLModel
from fastapi import Depends
from typing import Annotated, Generator
import os
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

# 1. Create the engine
engine = create_engine(os.environ["PG_URL"])

# 2. Define the session generator
def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

# 3. Define the SessionDep used in the routers
SessionDep = Annotated[Session, Depends(get_session)]

# 4. Table initialisation
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# 5. Idempotent column additions for existing tables (create_all does not ALTER existing tables)
_MIGRATIONS: tuple[str, ...] = ()


def run_migrations() -> None:
    with engine.begin() as conn:
        for stmt in _MIGRATIONS:
            conn.execute(text(stmt))