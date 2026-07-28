"""Task execution engine — the smallest complete slice of master §948-976.

Creates a `Task`, drives it through one `TaskRun` against a `ModelProvider`,
recording `Step`s and telemetry events at each transition. This is
intentionally single-shot and single-provider: planning/multi-step
orchestration, retries, and resource governance land in later phases once
there is a real reason (evidence) to need them.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.tasks.models import Step, StepKind, Task, TaskRun, TaskStatus
from acr.providers.base import CompletionRequest, ModelProvider
from acr.telemetry.recorder import TelemetryRecorder


async def run_task(
    session: AsyncSession,
    objective: str,
    provider: ModelProvider,
    telemetry: TelemetryRecorder,
) -> Task:
    """Run `objective` through `provider` end to end, committing the result."""
    task = Task(objective=objective)
    session.add(task)
    await session.flush()
    await telemetry.emit(session, "task.created", task_id=task.id, payload={"objective": objective})

    task.transition(TaskStatus.PLANNING)
    await telemetry.emit(
        session, "task.status_changed", task_id=task.id, payload={"status": task.status.value}
    )

    run = TaskRun(task_id=task.id, provider_name=provider.name)
    session.add(run)
    await session.flush()

    task.transition(TaskStatus.EXECUTING)
    await telemetry.emit(
        session, "task.status_changed", task_id=task.id, payload={"status": task.status.value}
    )

    session.add(
        Step(
            task_run_id=run.id,
            index=0,
            kind=StepKind.ACTION,
            name="model.complete",
            payload={"prompt": objective},
        )
    )
    await telemetry.emit(
        session, "model.call.started", task_id=task.id, payload={"provider": provider.name}
    )

    try:
        result = await provider.complete(CompletionRequest(prompt=objective))
    except Exception as exc:
        session.add(
            Step(
                task_run_id=run.id,
                index=1,
                kind=StepKind.OBSERVATION,
                name="model.error",
                payload={"error": f"{type(exc).__name__}: {exc}"},
            )
        )
        await telemetry.emit(
            session,
            "model.call.failed",
            task_id=task.id,
            payload={"provider": provider.name, "error": str(exc)},
        )
        run.status = TaskStatus.FAILED
        run.ended_at = datetime.now(UTC)
        task.transition(TaskStatus.FAILED)
        await telemetry.emit(session, "task.failed", task_id=task.id, payload={"reason": str(exc)})
        await session.commit()
        return task

    session.add(
        Step(
            task_run_id=run.id,
            index=1,
            kind=StepKind.OBSERVATION,
            name="model.result",
            payload={
                "text": result.text,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            },
        )
    )
    await telemetry.emit(
        session,
        "model.call.completed",
        task_id=task.id,
        payload={"provider": provider.name, "output_tokens": result.output_tokens},
    )

    task.transition(TaskStatus.VERIFYING)
    task.transition(TaskStatus.COMPLETED)
    run.status = TaskStatus.COMPLETED
    run.ended_at = datetime.now(UTC)

    await telemetry.emit(
        session, "task.completed", task_id=task.id, payload={"status": task.status.value}
    )
    await session.commit()
    return task
