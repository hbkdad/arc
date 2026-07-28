"""Tests for acr.memory.retrieval (master §530-551)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory import MemoryCandidate, MemoryScope, MemoryType
from acr.memory.retrieval import retrieve
from acr.memory.write_controller import remember


async def _seed(session: AsyncSession, subject: str, content: str, **overrides: object) -> None:
    defaults: dict[str, object] = dict(
        type=MemoryType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        subject=subject,
        content=content,
        source_type="session",
        confidence=0.9,
        evidence="test fixture",
    )
    defaults.update(overrides)
    await remember(session, MemoryCandidate(**defaults))  # type: ignore[arg-type]


async def test_retrieve_matches_a_sentence_query_via_or_semantics(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, "acr.db", "ACR persists data in a local SQLite file.")
    await _seed(db_session, "acr.ui", "The dashboard uses Next.js and React.")

    results = await retrieve(db_session, query="Explain the SQLite storage layer")

    assert len(results) == 1
    assert "SQLite" in results[0].record.content


async def test_retrieve_finds_matching_content_via_fts(db_session: AsyncSession) -> None:
    await _seed(db_session, "acr.db", "ACR persists data in a local SQLite file.")
    await _seed(db_session, "acr.ui", "The dashboard is built with Next.js and React.")

    results = await retrieve(db_session, query="SQLite")

    assert len(results) == 1
    assert "SQLite" in results[0].record.content
    assert results[0].relevance > 0


async def test_retrieve_filters_by_scope(db_session: AsyncSession) -> None:
    await _seed(db_session, "acr.db", "ACR persists data in a local SQLite file.")
    await _seed(
        db_session,
        "acr.db",
        "ACR persists data in a local SQLite file, per project X.",
        scope=MemoryScope.SESSION,
    )

    project_only = await retrieve(db_session, query="SQLite", scope=MemoryScope.PROJECT)

    assert all(item.record.scope is MemoryScope.PROJECT for item in project_only)


async def test_retrieve_respects_token_budget(db_session: AsyncSession) -> None:
    for i in range(5):
        await _seed(db_session, f"acr.topic.{i}", f"fact number {i} about ACR internals")

    results = await retrieve(db_session, query="ACR", token_budget=1)

    assert len(results) <= 1


async def test_retrieve_records_access_stats(db_session: AsyncSession) -> None:
    await _seed(db_session, "acr.db", "ACR persists data in a local SQLite file.")

    results = await retrieve(db_session, query="SQLite")
    await db_session.commit()

    assert len(results) == 1
    assert results[0].record.access_count == 1
    assert results[0].record.last_accessed is not None


async def test_retrieve_with_blank_query_ranks_by_confidence_and_importance(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, "acr.a", "low importance fact", importance=0.1)
    await _seed(db_session, "acr.b", "high importance fact", importance=0.9)

    results = await retrieve(db_session, query="")

    assert len(results) == 2
    assert results[0].record.subject == "acr.b"
