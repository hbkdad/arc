"""SQLAlchemy async engine/session wiring for ACR's local SQLite store."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import ConnectionPoolEntry

from acr.config import Settings


class Base(DeclarativeBase):
    """Base class for all ACR ORM models."""


def _set_sqlite_pragmas(
    dbapi_connection: DBAPIConnection, _connection_record: ConnectionPoolEntry
) -> None:
    """WAL mode lets the dashboard's read-only polling (every 2s, `/api/graph`)
    proceed while `acr run` holds a write transaction open for the duration
    of a real (non-mock) model call -- SQLite's default rollback-journal mode
    takes an exclusive lock for that whole span, so a poll landing during a
    slow completion hits `database is locked` past the default 5s busy
    timeout. This is the first real multi-process contention ACR sees, not a
    data-volume problem. A generous busy_timeout is the second half of the
    fix: still fails eventually if something is actually stuck, but survives
    an ordinary slow completion instead of a bare 5s default.

    `synchronous=NORMAL` is WAL mode's standard pairing (SQLite's own docs
    recommend it): under WAL, `FULL` fsyncs on every commit for a durability
    guarantee this local single-user tool doesn't need, while `NORMAL`
    fsyncs only at WAL checkpoints -- the worst case is losing the last
    commit or two to an OS crash/power loss between checkpoints, never
    corruption. A real, meaningful per-commit cost cut (fsync is
    particularly slow on Windows) for a tool that commits once per
    `run_task()` call and per telemetry emit."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def make_engine(settings: Settings) -> AsyncEngine:
    """Create an async engine, ensuring the local data directory exists first."""
    settings.ensure_data_dir()
    engine = create_async_engine(settings.database_url, future=True)
    event.listens_for(engine.sync_engine, "connect")(_set_sqlite_pragmas)
    return engine


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(settings: Settings) -> AsyncIterator[AsyncSession]:
    """Open a short-lived engine + session for one unit of work, then dispose it."""
    engine = make_engine(settings)
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()
