"""Engine, table creation and the per-request session dependency."""

from __future__ import annotations

from typing import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = settings.database_url
        connect_args = {}
        if url.startswith("sqlite"):
            settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
            connect_args = {"check_same_thread": False}
        _engine = create_engine(url, connect_args=connect_args)
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.close()
    return _engine


def set_engine(engine) -> None:
    """Swap the engine (used by tests to point at a temporary database)."""
    global _engine
    _engine = engine


def init_db() -> None:
    from app.db import models  # noqa: F401  (register tables)
    SQLModel.metadata.create_all(get_engine())


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one DB session per request."""
    with Session(get_engine()) as session:
        yield session
