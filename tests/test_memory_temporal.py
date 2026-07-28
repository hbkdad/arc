"""Tests for acr.memory.temporal (master §577-591)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory import MemoryCandidate, MemoryScope, MemoryType
from acr.memory.temporal import at, current, history
from acr.memory.write_controller import remember

SUBJECT = "acr.backend.database"


async def test_current_returns_the_latest_confirmed_value(db_session: AsyncSession) -> None:
    await remember(
        db_session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject=SUBJECT,
            content="ACR used Firebase.",
            source_type="session",
            confidence=0.9,
            evidence="early prototype notes",
        ),
    )
    _, replacement = await remember(
        db_session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject=SUBJECT,
            content="ACR uses SQLite.",
            source_type="session",
            confidence=0.9,
            evidence="pyproject.toml dependencies",
        ),
    )

    assert replacement is not None
    latest = await current(db_session, SUBJECT)
    assert latest is not None
    assert latest.id == replacement.id
    assert latest.content == "ACR uses SQLite."


async def test_at_returns_the_value_valid_at_a_past_timestamp(db_session: AsyncSession) -> None:
    _, original = await remember(
        db_session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject=SUBJECT,
            content="ACR used Firebase.",
            source_type="session",
            confidence=0.9,
            evidence="early prototype notes",
        ),
    )
    assert original is not None
    midpoint = datetime.now(UTC)

    await remember(
        db_session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject=SUBJECT,
            content="ACR uses SQLite.",
            source_type="session",
            confidence=0.9,
            evidence="pyproject.toml dependencies",
        ),
    )

    past_value = await at(db_session, SUBJECT, midpoint)
    assert past_value is not None
    assert past_value.id == original.id

    future_value = await at(db_session, SUBJECT, datetime.now(UTC) + timedelta(days=1))
    assert future_value is not None
    assert future_value.content == "ACR uses SQLite."


async def test_history_preserves_every_superseded_record(db_session: AsyncSession) -> None:
    for content in ("v1", "v2", "v3"):
        await remember(
            db_session,
            MemoryCandidate(
                type=MemoryType.SEMANTIC,
                scope=MemoryScope.PROJECT,
                subject=SUBJECT,
                content=content,
                source_type="session",
                confidence=0.9,
                evidence="test",
            ),
        )

    records = await history(db_session, SUBJECT)
    assert [record.content for record in records] == ["v1", "v2", "v3"]
