"""Tests for acr.learning.consolidation."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from acr.learning.consolidation import apply_gc_plan, plan_gc
from acr.memory import MemoryCandidate, MemoryScope, MemoryStatus, MemoryType
from acr.memory.models import utcnow
from acr.memory.write_controller import remember


async def _write(
    session: AsyncSession, *, status: MemoryStatus, age_days: int, **overrides: object
):
    defaults: dict[str, object] = dict(
        type=MemoryType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        subject="acr.gc.test",
        content="a memory record for GC testing",
        source_type="session",
        confidence=0.9,
        evidence="observed directly",
    )
    defaults.update(overrides)
    _evaluation, record = await remember(session, MemoryCandidate(**defaults))  # type: ignore[arg-type]
    assert record is not None
    record.status = status
    record.updated_at = utcnow() - timedelta(days=age_days)
    await session.flush()
    return record


async def test_a_fresh_confirmed_record_is_never_eligible(db_session: AsyncSession) -> None:
    await _write(db_session, status=MemoryStatus.CONFIRMED, age_days=0)

    plan = await plan_gc(db_session)

    assert plan.actions == []


async def test_an_old_confirmed_record_is_still_never_eligible(db_session: AsyncSession) -> None:
    # CONFIRMED never expires on a timer at any age -- only real
    # supersession retires a confirmed fact.
    await _write(db_session, status=MemoryStatus.CONFIRMED, age_days=9999)

    plan = await plan_gc(db_session)

    assert plan.actions == []


async def test_a_recently_superseded_record_is_not_yet_eligible(db_session: AsyncSession) -> None:
    await _write(db_session, status=MemoryStatus.SUPERSEDED, age_days=5)

    plan = await plan_gc(db_session, superseded_retention_days=30)

    assert plan.actions == []


async def test_an_old_superseded_record_is_eligible_for_archival(db_session: AsyncSession) -> None:
    record = await _write(db_session, status=MemoryStatus.SUPERSEDED, age_days=45)

    plan = await plan_gc(db_session, superseded_retention_days=30)

    assert len(plan.actions) == 1
    assert plan.actions[0].memory_id == record.id
    assert plan.actions[0].target_status is MemoryStatus.ARCHIVED


async def test_an_old_quarantined_record_is_eligible_for_archival(db_session: AsyncSession) -> None:
    record = await _write(db_session, status=MemoryStatus.QUARANTINED, age_days=20)

    plan = await plan_gc(db_session, quarantined_retention_days=14)

    assert len(plan.actions) == 1
    assert plan.actions[0].memory_id == record.id


async def test_a_stale_low_utility_candidate_is_eligible_for_archival(
    db_session: AsyncSession,
) -> None:
    record = await _write(db_session, status=MemoryStatus.CANDIDATE, age_days=90)
    record.utility_score = 0.0
    await db_session.flush()

    plan = await plan_gc(db_session, stale_candidate_days=60, stale_candidate_max_utility=0.2)

    assert len(plan.actions) == 1
    assert plan.actions[0].memory_id == record.id


async def test_a_stale_but_high_utility_candidate_is_not_eligible(db_session: AsyncSession) -> None:
    record = await _write(db_session, status=MemoryStatus.CANDIDATE, age_days=90)
    record.utility_score = 0.9
    await db_session.flush()

    plan = await plan_gc(db_session, stale_candidate_days=60, stale_candidate_max_utility=0.2)

    assert plan.actions == []


async def test_plan_gc_never_mutates_anything(db_session: AsyncSession) -> None:
    record = await _write(db_session, status=MemoryStatus.SUPERSEDED, age_days=45)

    await plan_gc(db_session, superseded_retention_days=30)

    assert record.status is MemoryStatus.SUPERSEDED


async def test_apply_gc_plan_archives_every_eligible_record(db_session: AsyncSession) -> None:
    record = await _write(db_session, status=MemoryStatus.SUPERSEDED, age_days=45)
    plan = await plan_gc(db_session, superseded_retention_days=30)

    applied = await apply_gc_plan(db_session, plan)

    assert applied == 1
    await db_session.refresh(record)
    assert record.status is MemoryStatus.ARCHIVED


async def test_apply_gc_plan_skips_a_record_that_changed_status_since_the_plan(
    db_session: AsyncSession,
) -> None:
    record = await _write(db_session, status=MemoryStatus.SUPERSEDED, age_days=45)
    plan = await plan_gc(db_session, superseded_retention_days=30)
    # Simulate the record being reviewed/changed between plan and apply.
    record.status = MemoryStatus.CONFIRMED
    await db_session.flush()

    applied = await apply_gc_plan(db_session, plan)

    assert applied == 0
    await db_session.refresh(record)
    assert record.status is MemoryStatus.CONFIRMED
