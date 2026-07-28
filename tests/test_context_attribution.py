"""Tests for acr.context.attribution (master §452-472)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.context.attribution import record_attribution
from acr.context.compiler import compile_context
from acr.memory import MemoryCandidate, MemoryScope, MemoryType
from acr.memory.write_controller import remember


async def _seed(session: AsyncSession, subject: str, content: str) -> None:
    await remember(
        session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject=subject,
            content=content,
            source_type="session",
            confidence=0.9,
            evidence="test fixture",
        ),
    )


async def test_referenced_items_get_successful_use_recorded(db_session: AsyncSession) -> None:
    await _seed(db_session, "acr.db", "ACR persists data in a local SQLite file.")
    bundle = await compile_context(db_session, task_objective="SQLite storage")
    assert len(bundle.items) == 1
    item = bundle.items[0]

    result = await record_attribution(db_session, bundle, used_item_ids={item.id}, success=True)
    await db_session.commit()

    assert result.referenced == [item]
    assert result.ignored == []


async def test_ignored_items_are_left_untouched(db_session: AsyncSession) -> None:
    await _seed(db_session, "acr.db", "ACR persists data in a local SQLite file.")
    await _seed(db_session, "acr.ui", "ACR dashboard uses SQLite-backed telemetry too.")
    bundle = await compile_context(db_session, task_objective="SQLite", token_budget=4000)
    assert len(bundle.items) == 2

    used = {bundle.items[0].id}
    result = await record_attribution(db_session, bundle, used_item_ids=used, success=True)

    assert len(result.referenced) == 1
    assert len(result.ignored) == 1
    assert result.ignored[0].id != result.referenced[0].id


async def test_failed_use_increments_failed_uses(db_session: AsyncSession) -> None:
    from sqlalchemy import select

    from acr.memory.models import MemoryRecord

    await _seed(db_session, "acr.db", "ACR persists data in a local SQLite file.")
    bundle = await compile_context(db_session, task_objective="SQLite storage")
    item = bundle.items[0]

    await record_attribution(db_session, bundle, used_item_ids={item.id}, success=False)
    await db_session.commit()

    record = (
        await db_session.execute(select(MemoryRecord).where(MemoryRecord.id == item.id))
    ).scalar_one()
    assert record.failed_uses == 1
    assert record.successful_uses == 0
    assert record.utility_score == 0.0
