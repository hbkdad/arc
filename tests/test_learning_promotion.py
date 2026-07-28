"""Tests for acr.learning.promotion (master §592-601)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.learning.promotion import promote_candidates
from acr.memory.models import MemoryRecord, MemoryScope, MemoryStatus, MemoryType


def _candidate_record(*, subject: str, utility_score: float, successful_uses: int) -> MemoryRecord:
    return MemoryRecord(
        type=MemoryType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        subject=subject,
        content=f"fact about {subject}",
        source_type="test",
        status=MemoryStatus.CANDIDATE,
        utility_score=utility_score,
        successful_uses=successful_uses,
    )


async def test_promote_candidates_promotes_records_meeting_both_thresholds(
    db_session: AsyncSession,
) -> None:
    record = _candidate_record(subject="acr.a", utility_score=0.9, successful_uses=5)
    db_session.add(record)
    await db_session.flush()

    report = await promote_candidates(db_session)

    assert record.status is MemoryStatus.CONFIRMED
    assert report.promoted == [record]
    assert report.considered == 1


async def test_promote_candidates_leaves_low_utility_records_alone(
    db_session: AsyncSession,
) -> None:
    record = _candidate_record(subject="acr.a", utility_score=0.2, successful_uses=5)
    db_session.add(record)
    await db_session.flush()

    report = await promote_candidates(db_session)

    assert record.status is MemoryStatus.CANDIDATE
    assert report.promoted == []
    assert report.considered == 1


async def test_promote_candidates_leaves_low_use_count_records_alone(
    db_session: AsyncSession,
) -> None:
    record = _candidate_record(subject="acr.a", utility_score=0.9, successful_uses=1)
    db_session.add(record)
    await db_session.flush()

    report = await promote_candidates(db_session)

    assert record.status is MemoryStatus.CANDIDATE
    assert report.promoted == []


async def test_promote_candidates_ignores_already_confirmed_records(
    db_session: AsyncSession,
) -> None:
    record = _candidate_record(subject="acr.a", utility_score=0.9, successful_uses=5)
    record.status = MemoryStatus.CONFIRMED
    db_session.add(record)
    await db_session.flush()

    report = await promote_candidates(db_session)

    assert report.considered == 0
    assert report.promoted == []


async def test_promote_candidates_respects_custom_thresholds(db_session: AsyncSession) -> None:
    record = _candidate_record(subject="acr.a", utility_score=0.5, successful_uses=1)
    db_session.add(record)
    await db_session.flush()

    report = await promote_candidates(db_session, min_utility=0.4, min_successful_uses=1)

    assert record.status is MemoryStatus.CONFIRMED
    assert report.promoted == [record]
