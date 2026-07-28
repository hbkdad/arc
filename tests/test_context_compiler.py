"""Tests for acr.context.compiler (master §411-450)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.context.compiler import compile_context
from acr.context.models import ContextSource
from acr.memory import MemoryCandidate, MemoryScope, MemoryType
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


async def test_compile_context_returns_matching_memory_as_items(db_session: AsyncSession) -> None:
    await _seed(db_session, "acr.db", "ACR persists data in a local SQLite file.")
    await _seed(db_session, "acr.ui", "The dashboard uses Next.js and React.")

    bundle = await compile_context(db_session, task_objective="Explain the SQLite storage layer")

    assert len(bundle.items) == 1
    item = bundle.items[0]
    assert item.source is ContextSource.MEMORY
    assert "SQLite" in item.content
    assert bundle.total_tokens == item.token_cost


async def test_compile_context_respects_token_budget(db_session: AsyncSession) -> None:
    for i in range(10):
        await _seed(db_session, f"acr.topic.{i}", f"fact number {i} about ACR internals " * 20)

    bundle = await compile_context(db_session, task_objective="ACR internals", token_budget=50)

    assert bundle.total_tokens <= 50


async def test_compile_context_deduplicates_identical_content(db_session: AsyncSession) -> None:
    # Two distinct subjects with identical content should collapse to one item.
    await _seed(db_session, "acr.a", "ACR uses SQLite.", scope=MemoryScope.PROJECT)
    await _seed(db_session, "acr.b", "ACR uses SQLite.", scope=MemoryScope.SESSION)

    bundle = await compile_context(db_session, task_objective="SQLite", token_budget=4000)

    assert len(bundle.items) == 1


async def test_compile_context_sets_constraints_and_objective(db_session: AsyncSession) -> None:
    bundle = await compile_context(db_session, task_objective="anything", token_budget=123)

    assert bundle.task_objective == "anything"
    assert bundle.constraints["token_budget"] == 123
    assert bundle.output_contract == {}
    assert bundle.verification_contract == {}
