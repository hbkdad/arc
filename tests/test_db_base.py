"""Tests for acr.db.base -- in particular, that _set_sqlite_pragmas()'s
pragmas actually take effect on a real connection, not just that the
event listener is wired up."""

from __future__ import annotations

from sqlalchemy import text

from acr.config import Settings
from acr.db.base import make_engine


async def test_sqlite_pragmas_actually_take_effect_on_a_real_connection(
    settings: Settings,
) -> None:
    engine = make_engine(settings)
    try:
        async with engine.connect() as conn:
            journal_mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
            synchronous = (await conn.execute(text("PRAGMA synchronous"))).scalar()
            busy_timeout = (await conn.execute(text("PRAGMA busy_timeout"))).scalar()
    finally:
        await engine.dispose()

    assert str(journal_mode).lower() == "wal"
    # SQLite reports `synchronous` back as its integer level, not the
    # keyword: 0=OFF, 1=NORMAL, 2=FULL.
    assert synchronous == 1
    assert busy_timeout == 30000
