"""Memory consolidation and lifecycle GC.

The conservative, opposite-direction mirror of
`acr.learning.promotion.promote_candidates()` (master §592-601): where
promotion graduates a `CANDIDATE` that earned trust, this retires memory
that's had its chance and didn't -- a stale, never-graduated `CANDIDATE`; a
`SUPERSEDED` record long past the point anything would still reference it;
a `QUARANTINED` record nobody ever reviewed. `CONFIRMED` records are never
touched at any age: earned trust doesn't expire on a timer, only real
supersession (the write controller's own job) retires a confirmed fact.

Two-step by design, `plan_gc()` then `apply_gc_plan()`, so nothing is ever
archived as a side effect of computing a plan -- the caller must see and
approve it first (master principle #22's evidence-before-action, applied
to *retiring* evidence rather than writing it).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory.models import MemoryRecord, MemoryStatus, MemoryType, utcnow
from acr.security.safe_mode import require_not_safe_mode

DEFAULT_SUPERSEDED_RETENTION_DAYS = 30
DEFAULT_QUARANTINED_RETENTION_DAYS = 14
DEFAULT_STALE_CANDIDATE_DAYS = 60
DEFAULT_STALE_CANDIDATE_MAX_UTILITY = 0.2

__all__ = [
    "DEFAULT_QUARANTINED_RETENTION_DAYS",
    "DEFAULT_STALE_CANDIDATE_DAYS",
    "DEFAULT_STALE_CANDIDATE_MAX_UTILITY",
    "DEFAULT_SUPERSEDED_RETENTION_DAYS",
    "GCAction",
    "GCPlan",
    "apply_gc_plan",
    "plan_gc",
]


@dataclass(frozen=True, slots=True)
class GCAction:
    memory_id: str
    subject: str
    type: MemoryType
    current_status: MemoryStatus
    target_status: MemoryStatus
    reason: str


@dataclass(frozen=True, slots=True)
class GCPlan:
    actions: list[GCAction]
    considered: int


def _archive(record: MemoryRecord, reason: str) -> GCAction:
    return GCAction(
        memory_id=record.id,
        subject=record.subject,
        type=record.type,
        current_status=record.status,
        target_status=MemoryStatus.ARCHIVED,
        reason=reason,
    )


async def plan_gc(
    session: AsyncSession,
    *,
    superseded_retention_days: int = DEFAULT_SUPERSEDED_RETENTION_DAYS,
    quarantined_retention_days: int = DEFAULT_QUARANTINED_RETENTION_DAYS,
    stale_candidate_days: int = DEFAULT_STALE_CANDIDATE_DAYS,
    stale_candidate_max_utility: float = DEFAULT_STALE_CANDIDATE_MAX_UTILITY,
) -> GCPlan:
    """Compute, but never apply, which records are eligible for archival."""
    stmt = select(MemoryRecord).where(
        MemoryRecord.status.in_(
            (MemoryStatus.SUPERSEDED, MemoryStatus.QUARANTINED, MemoryStatus.CANDIDATE)
        )
    )
    records = list((await session.execute(stmt)).scalars().all())

    actions: list[GCAction] = []
    for record in records:
        age_days = record.freshness_days
        if record.status is MemoryStatus.SUPERSEDED and age_days >= superseded_retention_days:
            actions.append(_archive(record, f"superseded {age_days:.0f}d ago"))
        elif record.status is MemoryStatus.QUARANTINED and age_days >= quarantined_retention_days:
            actions.append(_archive(record, f"quarantined {age_days:.0f}d, never reviewed"))
        elif (
            record.status is MemoryStatus.CANDIDATE
            and age_days >= stale_candidate_days
            and record.utility_score <= stale_candidate_max_utility
        ):
            actions.append(
                _archive(record, f"candidate {age_days:.0f}d old, never earned confirmation")
            )

    return GCPlan(actions=actions, considered=len(records))


async def apply_gc_plan(session: AsyncSession, plan: GCPlan, *, safe_mode: bool = False) -> int:
    """Apply a plan `plan_gc()` produced. Re-fetches each record by id and
    re-checks `current_status` rather than trusting the plan's in-memory
    snapshot, since the caller may review a plan across a separate
    request/process boundary before applying it (the CLI does exactly
    this: one invocation prints the plan, `--apply` on a second invocation
    actually mutates) -- a record that changed status in between is
    skipped, not fought over.

    `safe_mode.py`'s own docstring lists "memory deletion" as safe-mode
    -disabled; archival is exactly that operation, so this is gated the
    same way `skills.registry.set_status()` gates activation.
    """
    require_not_safe_mode(safe_mode, "memory.gc_apply")
    applied = 0
    for action in plan.actions:
        record = await session.get(MemoryRecord, action.memory_id)
        if record is None or record.status != action.current_status:
            continue
        record.status = action.target_status
        record.updated_at = utcnow()
        applied += 1
    if applied:
        await session.flush()
    return applied
