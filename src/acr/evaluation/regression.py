"""Regression detection over persisted benchmark runs (master §1662-1667,
§1061-1090: "Compare ... " runs of the same suite over time).

Compares the two most recent `BenchmarkRun`s for a suite. A single run in
isolation says nothing about regression — this only has an opinion once
there are at least two.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.benchmarks.models import BenchmarkRun

DEFAULT_THRESHOLD = 0.05


@dataclass(frozen=True, slots=True)
class RegressionReport:
    suite_name: str
    baseline: BenchmarkRun | None
    current: BenchmarkRun | None
    regressed: bool
    score_delta: float
    detail: str


async def _recent_runs(session: AsyncSession, suite_name: str, limit: int) -> list[BenchmarkRun]:
    stmt = (
        select(BenchmarkRun)
        .where(BenchmarkRun.suite_name == suite_name)
        .order_by(BenchmarkRun.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def detect_regression(
    session: AsyncSession, suite_name: str, *, threshold: float = DEFAULT_THRESHOLD
) -> RegressionReport:
    """Compare the two most recent runs of `suite_name`.

    `threshold` is an absolute drop in `score` (0.0-1.0) that counts as a
    regression — e.g. 0.05 means "more than 5 percentage points worse".
    """
    runs = await _recent_runs(session, suite_name, limit=2)

    if len(runs) < 2:
        return RegressionReport(
            suite_name=suite_name,
            baseline=None,
            current=runs[0] if runs else None,
            regressed=False,
            score_delta=0.0,
            detail="fewer than two runs recorded — nothing to compare yet",
        )

    current, baseline = runs
    delta = current.score - baseline.score
    regressed = delta < -threshold

    detail = (
        f"score {baseline.score:.3f} -> {current.score:.3f} (delta {delta:+.3f}, "
        f"threshold -{threshold:.3f})"
    )
    return RegressionReport(
        suite_name=suite_name,
        baseline=baseline,
        current=current,
        regressed=regressed,
        score_delta=delta,
        detail=detail,
    )
