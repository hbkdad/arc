"""Task explainability: replay a task's real telemetry trail, never a
generated narrative (informed by the reference repo's read-only runtime
inspection: "replays retained scoring and lifecycle facts, exposes
evidence gaps, never generates post-hoc narratives").

Every fact here is a straight read of `TelemetryEvent` rows
`core.execution.run_task()` already writes -- no new storage, no new
heuristic; this only imposes chronological order and a short computed
summary (provider used, tokens, duration) on data that already exists.
Honest about what ACR does *not* retain: `AgentSpec`/skill-routing
decisions are never persisted (an `AgentSpec` is an in-memory plan, not a
row), so a task spawned via `agents spawn` can't be traced back to which
skills were routed for it from this table alone -- only the model-call
and lifecycle trail can.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.tasks.models import Task
from acr.telemetry.models import TelemetryEvent

__all__ = ["TaskExplanation", "TaskNotFoundError", "explain_task"]


class TaskNotFoundError(LookupError):
    """Raised by `explain_task()` for an unknown task id."""


@dataclass(frozen=True, slots=True)
class TaskExplanation:
    task: Task
    events: list[TelemetryEvent]
    provider: str | None
    output_tokens: int | None
    duration_seconds: float | None


async def explain_task(session: AsyncSession, task_id: str) -> TaskExplanation:
    task = await session.get(Task, task_id)
    if task is None:
        raise TaskNotFoundError(task_id)

    stmt = (
        select(TelemetryEvent)
        .where(TelemetryEvent.task_id == task_id)
        .order_by(TelemetryEvent.created_at)
    )
    events = list((await session.execute(stmt)).scalars().all())

    provider: str | None = None
    output_tokens: int | None = None
    for event in events:
        candidate = event.payload.get("provider")
        if isinstance(candidate, str):
            provider = candidate
        if event.event_type == "model.call.completed":
            tokens = event.payload.get("output_tokens")
            if isinstance(tokens, int):
                output_tokens = tokens

    duration_seconds: float | None = None
    if len(events) >= 2:
        duration_seconds = (events[-1].created_at - events[0].created_at).total_seconds()

    return TaskExplanation(
        task=task,
        events=events,
        provider=provider,
        output_tokens=output_tokens,
        duration_seconds=duration_seconds,
    )
