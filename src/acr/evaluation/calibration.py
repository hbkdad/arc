"""Memory confidence calibration.

Reference-repo-informed (fixed-bin reliability curves, a Brier score) but
computed strictly from real accrued usage evidence already tracked on
every `MemoryRecord` -- `successful_uses`/`failed_uses`, the same counters
`acr.context.attribution` maintains -- never from a synthesized outcome.

Answers one question: does a memory's stored `confidence` actually predict
how often it turns out useful? A record with zero recorded uses has no
empirical outcome to compare its confidence against and is excluded
entirely, not scored as a 0% success rate (master principle #22: no
opinion without evidence). This is read-only and advisory -- it never
rewrites a record's confidence or any other field.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory.models import MemoryRecord

DEFAULT_MIN_USES = 1
# 1.01 as the final upper edge so a record with confidence exactly 1.0
# still falls inside the last [0.8, 1.0] bin rather than being dropped by
# a strict `< 1.0` upper bound.
DEFAULT_BIN_EDGES: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.01)

__all__ = [
    "DEFAULT_BIN_EDGES",
    "DEFAULT_MIN_USES",
    "CalibrationBin",
    "CalibrationReport",
    "compute_calibration",
]


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_confidence: float
    empirical_success_rate: float


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    bins: list[CalibrationBin]
    records_considered: int
    records_excluded_no_evidence: int
    brier_score: float | None


def _empirical_rate(record: MemoryRecord) -> float:
    total = record.successful_uses + record.failed_uses
    return record.successful_uses / total


async def compute_calibration(
    session: AsyncSession,
    *,
    min_uses: int = DEFAULT_MIN_USES,
    bin_edges: tuple[float, ...] = DEFAULT_BIN_EDGES,
) -> CalibrationReport:
    """Fixed-bin reliability curve + Brier score over every memory record
    with at least `min_uses` real recorded uses (successful + failed)."""
    all_records = list((await session.execute(select(MemoryRecord))).scalars().all())
    evidenced = [r for r in all_records if (r.successful_uses + r.failed_uses) >= min_uses]
    excluded = len(all_records) - len(evidenced)

    bins: list[CalibrationBin] = []
    for lower, upper in pairwise(bin_edges):
        in_bin = [r for r in evidenced if lower <= r.confidence < upper]
        if not in_bin:
            continue
        mean_conf = sum(r.confidence for r in in_bin) / len(in_bin)
        mean_rate = sum(_empirical_rate(r) for r in in_bin) / len(in_bin)
        bins.append(
            CalibrationBin(
                lower=lower,
                upper=min(upper, 1.0),
                count=len(in_bin),
                mean_confidence=mean_conf,
                empirical_success_rate=mean_rate,
            )
        )

    brier_score = None
    if evidenced:
        brier_score = sum((r.confidence - _empirical_rate(r)) ** 2 for r in evidenced) / len(
            evidenced
        )

    return CalibrationReport(
        bins=bins,
        records_considered=len(evidenced),
        records_excluded_no_evidence=excluded,
        brier_score=brier_score,
    )
