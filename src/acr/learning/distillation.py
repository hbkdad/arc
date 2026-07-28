"""Experience distillation (master §631-644).

Converts a completed Task's raw execution trace (its TaskRuns and Steps)
into a compact, structured memory candidate. Tracks the compression ratio
achieved (master §644). Raw traces are never deleted or duplicated into
memory — they stay exactly where Phase 1 already put them
(`tasks`/`task_runs`/`steps`), "outside normal context" (§642): the context
compiler (Phase 3) only ever reads `memory_records`, never these tables.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.tasks.models import Step, Task, TaskRun, TaskStatus
from acr.memory.models import MemoryScope, MemoryType
from acr.memory.write_controller import MemoryCandidate, WriteEvaluation, remember


class TaskNotFoundError(LookupError):
    """Raised when distillation targets an unknown task id."""


@dataclass(frozen=True, slots=True)
class DistillationResult:
    task_id: str
    raw_trace_bytes: int
    distilled_bytes: int
    memory_candidate: MemoryCandidate | None
    reason: str

    @property
    def compression_ratio(self) -> float:
        """>1.0 means the distilled form is smaller than the raw trace."""
        if self.distilled_bytes == 0:
            return 0.0
        return self.raw_trace_bytes / self.distilled_bytes


async def distill_task(session: AsyncSession, task_id: str) -> DistillationResult:
    """Distill one Task's trace. Only a COMPLETED task yields a memory
    candidate — a distilled "lesson" from a task that didn't finish would be
    exactly the kind of unevidenced claim master principle #22 forbids.
    """
    task = await session.get(Task, task_id)
    if task is None:
        raise TaskNotFoundError(task_id)

    runs = list(
        (await session.execute(select(TaskRun).where(TaskRun.task_id == task_id))).scalars().all()
    )
    steps: list[Step] = []
    for run in runs:
        steps.extend(
            (await session.execute(select(Step).where(Step.task_run_id == run.id))).scalars().all()
        )

    raw_trace = {
        "task": {"id": task.id, "objective": task.objective, "status": task.status.value},
        "runs": [{"id": r.id, "provider": r.provider_name, "status": r.status.value} for r in runs],
        "steps": [{"kind": s.kind.value, "name": s.name, "payload": s.payload} for s in steps],
    }
    raw_bytes = len(json.dumps(raw_trace))

    if task.status is not TaskStatus.COMPLETED:
        distilled = {"task_id": task.id, "outcome": task.status.value}
        return DistillationResult(
            task_id=task.id,
            raw_trace_bytes=raw_bytes,
            distilled_bytes=len(json.dumps(distilled)),
            memory_candidate=None,
            reason=f"task status is {task.status.value}, not completed",
        )

    provider_names = sorted({r.provider_name for r in runs})
    content = (
        f"Task '{task.objective}' completed successfully via "
        f"{', '.join(provider_names) or 'an unrecorded provider'}."
    )
    candidate = MemoryCandidate(
        type=MemoryType.EPISODIC,
        scope=MemoryScope.PROJECT,
        subject=f"task.{task.id}",
        content=content,
        source_type="experience_distillation",
        source_id=task.id,
        confidence=0.7,
        evidence=f"task_run:{runs[0].id}" if runs else f"task:{task.id}",
    )
    distilled_bytes = len(json.dumps({"content": content}))

    return DistillationResult(
        task_id=task.id,
        raw_trace_bytes=raw_bytes,
        distilled_bytes=distilled_bytes,
        memory_candidate=candidate,
        reason="distilled",
    )


async def distill_and_remember(
    session: AsyncSession, task_id: str
) -> tuple[DistillationResult, WriteEvaluation | None]:
    """`distill_task()`, then hand any resulting candidate to the write
    controller (master §553-575) — distillation proposes, it doesn't grant
    itself confirmed memory."""
    result = await distill_task(session, task_id)
    if result.memory_candidate is None:
        return result, None
    evaluation, _record = await remember(session, result.memory_candidate)
    return result, evaluation
