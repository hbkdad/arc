"""Token waste analysis (master §1026-1039).

Two concrete detectors, both grounded in data ACR actually has:

- duplicate memory content across different subjects (§1029 "duplicate
  context" — `write_controller` already prevents duplicates *within* the
  same subject/scope/type, but the same fact can still be stored under two
  different subjects).
- context utilization from persisted `context.attribution` telemetry events
  (§1027 "unused context") — the fraction of compiled-context tokens that
  were actually referenced by the task that requested them.

The other listed waste categories (oversized system prompts, unused tool
definitions, unused skills, excessive agent coordination, unnecessary
reflection/escalation) need subsystems that don't exist yet (tools, agents,
routing-with-escalation) and are deliberately not stubbed here — master
principle #23: no feature expansion without measurable value.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory.models import MemoryRecord, MemoryStatus
from acr.telemetry.models import TelemetryEvent

_ACTIVE_STATUSES = (MemoryStatus.CANDIDATE, MemoryStatus.CONFIRMED)


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    content: str
    record_ids: list[str]


async def find_duplicate_memories(session: AsyncSession) -> list[DuplicateGroup]:
    """Active memory records with byte-identical content under different subjects."""
    stmt = select(MemoryRecord).where(MemoryRecord.status.in_(_ACTIVE_STATUSES))
    records = (await session.execute(stmt)).scalars().all()

    by_content: dict[str, list[MemoryRecord]] = defaultdict(list)
    for record in records:
        by_content[record.content].append(record)

    return [
        DuplicateGroup(content=content, record_ids=[r.id for r in group])
        for content, group in by_content.items()
        if len(group) > 1
    ]


@dataclass(frozen=True, slots=True)
class UtilizationReport:
    sample_count: int
    total_bundle_tokens: int
    total_referenced_tokens: int

    @property
    def utilization(self) -> float:
        if self.total_bundle_tokens == 0:
            return 1.0
        return self.total_referenced_tokens / self.total_bundle_tokens

    @property
    def wasted_tokens(self) -> int:
        return self.total_bundle_tokens - self.total_referenced_tokens


async def analyze_context_utilization(
    session: AsyncSession, *, limit: int = 200
) -> UtilizationReport:
    """Aggregate recorded `context.attribution` telemetry events into a
    utilization report (see `acr.context.attribution.record_attribution`)."""
    stmt = (
        select(TelemetryEvent)
        .where(TelemetryEvent.event_type == "context.attribution")
        .order_by(TelemetryEvent.created_at.desc())
        .limit(limit)
    )
    events = (await session.execute(stmt)).scalars().all()

    total_bundle = sum(event.payload.get("bundle_tokens", 0) for event in events)
    total_referenced = sum(event.payload.get("referenced_tokens", 0) for event in events)

    return UtilizationReport(
        sample_count=len(events),
        total_bundle_tokens=total_bundle,
        total_referenced_tokens=total_referenced,
    )
