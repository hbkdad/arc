"""SQLAlchemy async engine/session wiring for ACR's local SQLite store."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from acr.config import Settings


class Base(DeclarativeBase):
    """Base class for all ACR ORM models."""


def make_engine(settings: Settings) -> AsyncEngine:
    """Create an async engine, ensuring the local data directory exists first."""
    settings.ensure_data_dir()
    return create_async_engine(settings.database_url, future=True)


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
