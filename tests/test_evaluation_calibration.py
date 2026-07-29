"""Tests for acr.evaluation.calibration."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.evaluation.calibration import compute_calibration
from acr.memory import MemoryCandidate, MemoryScope, MemoryType
from acr.memory.write_controller import remember


async def _seed(
    session: AsyncSession, *, confidence: float, successful_uses: int, failed_uses: int
) -> None:
    _evaluation, record = await remember(
        session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject=f"acr.calibration.test.{successful_uses}.{failed_uses}",
            content="a memory record for calibration testing",
            source_type="session",
            confidence=confidence,
            evidence="observed directly",
        ),
    )
    assert record is not None
    record.successful_uses = successful_uses
    record.failed_uses = failed_uses
    await session.flush()


async def test_a_record_with_no_recorded_uses_is_excluded(db_session: AsyncSession) -> None:
    await _seed(db_session, confidence=0.9, successful_uses=0, failed_uses=0)

    report = await compute_calibration(db_session)

    assert report.records_considered == 0
    assert report.records_excluded_no_evidence == 1
    assert report.brier_score is None
    assert report.bins == []


async def test_a_well_calibrated_record_lands_in_the_right_bin(db_session: AsyncSession) -> None:
    # confidence=0.9, empirical rate 9/10=0.9 -- a well-calibrated record.
    await _seed(db_session, confidence=0.9, successful_uses=9, failed_uses=1)

    report = await compute_calibration(db_session)

    assert report.records_considered == 1
    assert len(report.bins) == 1
    b = report.bins[0]
    assert b.lower == 0.8
    assert b.count == 1
    assert b.mean_confidence == 0.9
    assert b.empirical_success_rate == 0.9
    assert report.brier_score == 0.0


async def test_an_overconfident_record_produces_a_nonzero_brier_score(
    db_session: AsyncSession,
) -> None:
    # confidence=0.9 but only 20% actually succeeded -- badly overconfident.
    await _seed(db_session, confidence=0.9, successful_uses=1, failed_uses=4)

    report = await compute_calibration(db_session)

    assert report.records_considered == 1
    assert report.brier_score is not None
    assert report.brier_score > 0.4  # (0.9 - 0.2)^2 = 0.49


async def test_min_uses_excludes_a_record_below_the_threshold(db_session: AsyncSession) -> None:
    await _seed(db_session, confidence=0.9, successful_uses=1, failed_uses=0)

    report = await compute_calibration(db_session, min_uses=3)

    assert report.records_considered == 0
    assert report.records_excluded_no_evidence == 1


async def test_multiple_records_in_the_same_bin_are_averaged(db_session: AsyncSession) -> None:
    await _seed(db_session, confidence=0.85, successful_uses=8, failed_uses=2)  # rate 0.8
    await _seed(db_session, confidence=0.95, successful_uses=10, failed_uses=0)  # rate 1.0

    report = await compute_calibration(db_session)

    assert report.records_considered == 2
    assert len(report.bins) == 1
    b = report.bins[0]
    assert b.count == 2
    assert b.mean_confidence == pytest.approx(0.9)
    assert b.empirical_success_rate == pytest.approx(0.9)


async def test_returns_an_empty_report_with_no_records_at_all(db_session: AsyncSession) -> None:
    report = await compute_calibration(db_session)

    assert report.bins == []
    assert report.records_considered == 0
    assert report.records_excluded_no_evidence == 0
    assert report.brier_score is None
