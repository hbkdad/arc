"""Tests for acr.evaluation.regression."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.benchmarks.models import BenchmarkRun
from acr.evaluation.regression import detect_regression


async def _make_run(session: AsyncSession, suite: str, score: float) -> BenchmarkRun:
    run = BenchmarkRun(
        suite_name=suite, total_cases=10, passed_cases=round(score * 10), score=score, details={}
    )
    session.add(run)
    await session.flush()
    return run


async def test_detect_regression_with_no_runs_reports_nothing_to_compare(
    db_session: AsyncSession,
) -> None:
    report = await detect_regression(db_session, "never-run-suite")

    assert report.regressed is False
    assert report.baseline is None
    assert "fewer than two" in report.detail


async def test_detect_regression_with_one_run_reports_nothing_to_compare(
    db_session: AsyncSession,
) -> None:
    await _make_run(db_session, "suite-a", 0.9)

    report = await detect_regression(db_session, "suite-a")

    assert report.regressed is False
    assert report.baseline is None


async def test_detect_regression_flags_a_score_drop_past_threshold(
    db_session: AsyncSession,
) -> None:
    await _make_run(db_session, "suite-a", 0.9)
    await _make_run(db_session, "suite-a", 0.5)

    report = await detect_regression(db_session, "suite-a", threshold=0.05)

    assert report.regressed is True
    assert report.score_delta < 0


async def test_detect_regression_ignores_a_small_drop_within_threshold(
    db_session: AsyncSession,
) -> None:
    await _make_run(db_session, "suite-a", 0.90)
    await _make_run(db_session, "suite-a", 0.89)

    report = await detect_regression(db_session, "suite-a", threshold=0.05)

    assert report.regressed is False


async def test_detect_regression_ignores_an_improvement(db_session: AsyncSession) -> None:
    await _make_run(db_session, "suite-a", 0.5)
    await _make_run(db_session, "suite-a", 0.9)

    report = await detect_regression(db_session, "suite-a")

    assert report.regressed is False
    assert report.score_delta > 0


async def test_detect_regression_only_compares_the_same_suite(db_session: AsyncSession) -> None:
    await _make_run(db_session, "suite-a", 0.9)
    await _make_run(db_session, "suite-b", 0.1)

    report = await detect_regression(db_session, "suite-a")

    assert report.baseline is None  # only one "suite-a" run exists
