"""Context attribution (master §452-472).

After a task executes, determine which selected context items actually
contributed, and feed that back into each source's historical utility (e.g.
`MemoryRecord.successful_uses` / `failed_uses`). Attribution here is
*explicit* — the caller states which item IDs were used — rather than
inferred by a judge model; inference is exactly the "evaluator judgment"
§471 lists as a valid attribution signal, but that needs Phase 5's
evaluation system, not Phase 3's compiler.

Per master §464-465: an ignored item is not assumed useless. Only items the
caller explicitly marks as used have their utility updated.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.context.models import ContextBundle, ContextItem, ContextSource
from acr.memory.models import MemoryRecord
from acr.telemetry.recorder import TelemetryRecorder


@dataclass(frozen=True, slots=True)
class AttributionResult:
    referenced: list[ContextItem]
    ignored: list[ContextItem]


async def record_attribution(
    session: AsyncSession,
    bundle: ContextBundle,
    *,
    used_item_ids: set[str],
    success: bool,
    telemetry: TelemetryRecorder | None = None,
    task_id: str | None = None,
) -> AttributionResult:
    """Mark which bundle items were used and update their source's utility.

    `success` is the outcome of the task that consumed `bundle`: a used
    item's owning record gets `successful_uses` or `failed_uses`
    incremented, and `utility_score` recomputed from the new ratio.

    If `telemetry` is given, also emits a `context.attribution` event
    (bundle/referenced token counts) — this is what
    `acr.evaluation.waste_analyzer.analyze_context_utilization` reads to
    report unused-context waste (master §1027) over time.
    """
    referenced = [item for item in bundle.items if item.id in used_item_ids]
    ignored = [item for item in bundle.items if item.id not in used_item_ids]

    memory_ids = {item.id for item in referenced if item.source is ContextSource.MEMORY}
    if memory_ids:
        records = (
            (await session.execute(select(MemoryRecord).where(MemoryRecord.id.in_(memory_ids))))
            .scalars()
            .all()
        )
        for record in records:
            if success:
                record.successful_uses += 1
            else:
                record.failed_uses += 1
            total = record.successful_uses + record.failed_uses
            record.utility_score = record.successful_uses / total if total else 0.0

    if telemetry is not None:
        await telemetry.emit(
            session,
            "context.attribution",
            task_id=task_id,
            payload={
                "bundle_tokens": bundle.total_tokens,
                "referenced_tokens": sum(item.token_cost for item in referenced),
                "referenced_count": len(referenced),
                "ignored_count": len(ignored),
            },
        )

    return AttributionResult(referenced=referenced, ignored=ignored)
