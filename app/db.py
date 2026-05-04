from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import sqlite_vec
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
engine = create_async_engine(_settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _enable_sqlite_extensions(dbapi_conn: Any, _connection_record: Any) -> None:
    """Connect-event handler: enable WAL, FK enforcement, and load sqlite-vec.

    Works with both the sync ``sqlite3.Connection`` and SQLAlchemy's
    ``AsyncAdapt_aiosqlite_connection`` (which wraps an
    ``aiosqlite.Connection``, which wraps the real ``sqlite3.Connection``).
    PRAGMAs go through the dbapi adapter (which the async wrapper proxies
    correctly); ``enable_load_extension`` and ``sqlite_vec.load`` need the
    raw sqlite3 connection because the async wrapper exposes them as
    coroutines that can't be awaited from inside a sync event handler.
    """
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA foreign_keys=ON")

    # Drill through any async/aiosqlite wrappers to reach sqlite3.Connection.
    raw: Any = dbapi_conn
    for attr in ("_connection", "_conn"):
        nested = getattr(raw, attr, None)
        if nested is not None:
            raw = nested
    raw.enable_load_extension(True)
    sqlite_vec.load(raw)
    raw.enable_load_extension(False)


def attach_sqlite_extensions(sync_engine: Engine) -> None:
    """Attach the sqlite-vec / pragma loader to a sync engine.

    Used by alembic's env.py since alembic builds its own engine that doesn't
    inherit listeners from the app's engine.
    """
    event.listen(sync_engine, "connect", _enable_sqlite_extensions)


# Attach to the app's engine
attach_sqlite_extensions(engine.sync_engine)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
