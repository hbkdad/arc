"""Tests for acr.core.execution.run_task."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.execution import run_task
from acr.core.tasks.models import Step, TaskRun, TaskStatus
from acr.providers.mock import MockProvider
from acr.telemetry.models import TelemetryEvent
from acr.telemetry.recorder import TelemetryRecorder


async def test_run_task_completes_with_mock_provider(db_session: AsyncSession) -> None:
    task = await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    assert task.status is TaskStatus.COMPLETED
    assert task.is_terminal


async def test_run_task_persists_run_and_steps(db_session: AsyncSession) -> None:
    task = await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    runs = (
        (await db_session.execute(select(TaskRun).where(TaskRun.task_id == task.id)))
        .scalars()
        .all()
    )
    assert len(runs) == 1
    assert runs[0].status is TaskStatus.COMPLETED
    assert runs[0].provider_name == "mock"

    steps = (
        (await db_session.execute(select(Step).where(Step.task_run_id == runs[0].id)))
        .scalars()
        .all()
    )
    assert [step.name for step in sorted(steps, key=lambda s: s.index)] == [
        "model.complete",
        "model.result",
    ]


async def test_run_task_records_telemetry_events(db_session: AsyncSession) -> None:
    task = await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    events = (
        (await db_session.execute(select(TelemetryEvent).where(TelemetryEvent.task_id == task.id)))
        .scalars()
        .all()
    )
    event_types = [event.event_type for event in events]
    assert "task.created" in event_types
    assert "model.call.completed" in event_types
    assert "task.completed" in event_types
