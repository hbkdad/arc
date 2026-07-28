"""Candidate memory promotion (master §592-601: "promote useful patterns";
§566-575: `STORE_CANDIDATE` is a first step, not a permanent state).

A `CANDIDATE` memory graduates to `CONFIRMED` once it has earned enough
accumulated evidence of usefulness — `utility_score` and `successful_uses`
are exactly the numbers `acr.context.attribution` already maintains.
Promotion also raises the record's trust level (Phase 7:
`memory_trust_level()` maps `CONFIRMED` -> `VERIFIED_MEMORY`), so this is
the mechanism by which a memory actually earns higher trust over time.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory.models import MemoryRecord, MemoryStatus, utcnow

DEFAULT_MIN_UTILITY = 0.7
DEFAULT_MIN_SUCCESSFUL_USES = 3


@dataclass(frozen=True, slots=True)
class PromotionReport:
    promoted: list[MemoryRecord]
    considered: int


async def promote_candidates(
    session: AsyncSession,
    *,
    min_utility: float = DEFAULT_MIN_UTILITY,
    min_successful_uses: int = DEFAULT_MIN_SUCCESSFUL_USES,
) -> PromotionReport:
    """Promote every `CANDIDATE` record meeting both thresholds to `CONFIRMED`."""
    stmt = select(MemoryRecord).where(MemoryRecord.status == MemoryStatus.CANDIDATE)
    candidates = list((await session.execute(stmt)).scalars().all())

    promoted: list[MemoryRecord] = []
    for record in candidates:
        if record.utility_score >= min_utility and record.successful_uses >= min_successful_uses:
            record.status = MemoryStatus.CONFIRMED
            record.updated_at = utcnow()
            promoted.append(record)

    if promoted:
        await session.flush()
    return PromotionReport(promoted=promoted, considered=len(candidates))
