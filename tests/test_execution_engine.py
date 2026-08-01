"""Tests for acr.core.execution.run_task."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.execution import run_task
from acr.core.tasks.models import Step, TaskRun, TaskStatus
from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider
from acr.providers.mock import MockProvider
from acr.telemetry.models import TelemetryEvent
from acr.telemetry.recorder import TelemetryRecorder


class _AlwaysFailsProvider(ModelProvider):
    name = "always-fails"

    async def is_available(self) -> bool:
        return True

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        raise RuntimeError("simulated provider failure")


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


async def test_run_task_marks_the_task_and_run_failed_when_the_provider_raises(
    db_session: AsyncSession,
) -> None:
    # The except-branch in run_task() had never executed under test --
    # MockProvider never raises, so a real provider timeout/500 leaving
    # run/task status wrong would previously have gone uncaught.
    task = await run_task(db_session, "say hello", _AlwaysFailsProvider(), TelemetryRecorder())

    assert task.status is TaskStatus.FAILED
    assert task.is_terminal

    runs = (
        (await db_session.execute(select(TaskRun).where(TaskRun.task_id == task.id)))
        .scalars()
        .all()
    )
    assert len(runs) == 1
    assert runs[0].status is TaskStatus.FAILED
    assert runs[0].ended_at is not None

    steps = (
        (await db_session.execute(select(Step).where(Step.task_run_id == runs[0].id)))
        .scalars()
        .all()
    )
    assert [step.name for step in sorted(steps, key=lambda s: s.index)] == [
        "model.complete",
        "model.error",
    ]
    error_step = next(s for s in steps if s.name == "model.error")
    assert "simulated provider failure" in error_step.payload["error"]

    events = (
        (await db_session.execute(select(TelemetryEvent).where(TelemetryEvent.task_id == task.id)))
        .scalars()
        .all()
    )
    event_types = [event.event_type for event in events]
    assert "model.call.failed" in event_types
    assert "task.failed" in event_types


async def test_run_task_redacts_secrets_in_step_payloads(db_session: AsyncSession) -> None:
    # TelemetryEvent payloads already pass through redact_mapping() via
    # TelemetryRecorder -- Step payloads (written directly by run_task(),
    # not through the recorder) previously didn't, so a secret pasted into
    # an objective landed verbatim in the steps table.
    secret_objective = "my key is sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX, help me"
    task = await run_task(db_session, secret_objective, MockProvider(), TelemetryRecorder())

    runs = (
        (await db_session.execute(select(TaskRun).where(TaskRun.task_id == task.id)))
        .scalars()
        .all()
    )
    steps = (
        (await db_session.execute(select(Step).where(Step.task_run_id == runs[0].id)))
        .scalars()
        .all()
    )
    prompt_step = next(s for s in steps if s.name == "model.complete")
    result_step = next(s for s in steps if s.name == "model.result")
    assert "sk-ant-api03-" not in prompt_step.payload["prompt"]
    assert "[REDACTED]" in prompt_step.payload["prompt"]
    assert "sk-ant-api03-" not in result_step.payload["text"]
