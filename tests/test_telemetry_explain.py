"""Tests for acr.telemetry.explain."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.execution import run_task
from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider
from acr.providers.mock import MockProvider
from acr.telemetry.explain import TaskNotFoundError, explain_task
from acr.telemetry.recorder import TelemetryRecorder


class _AlwaysFailsProvider(ModelProvider):
    name = "always-fails"

    async def is_available(self) -> bool:
        return True

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        raise RuntimeError("simulated provider failure")


async def test_raises_for_an_unknown_task_id(db_session: AsyncSession) -> None:
    with pytest.raises(TaskNotFoundError):
        await explain_task(db_session, "does-not-exist")


async def test_explains_a_completed_task(db_session: AsyncSession) -> None:
    task = await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    explanation = await explain_task(db_session, task.id)

    assert explanation.task.id == task.id
    assert explanation.provider == "mock"
    assert explanation.output_tokens is not None and explanation.output_tokens > 0
    event_types = [e.event_type for e in explanation.events]
    assert event_types == [
        "task.created",
        "task.status_changed",
        "task.status_changed",
        "model.call.started",
        "model.call.completed",
        "task.completed",
    ]


async def test_explains_a_failed_task_with_no_output_tokens(db_session: AsyncSession) -> None:
    task = await run_task(db_session, "say hello", _AlwaysFailsProvider(), TelemetryRecorder())

    explanation = await explain_task(db_session, task.id)

    assert explanation.provider == "always-fails"
    assert explanation.output_tokens is None
    assert "model.call.failed" in [e.event_type for e in explanation.events]
    assert "task.failed" in [e.event_type for e in explanation.events]


async def test_events_are_returned_in_chronological_order(db_session: AsyncSession) -> None:
    task = await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    explanation = await explain_task(db_session, task.id)

    timestamps = [e.created_at for e in explanation.events]
    assert timestamps == sorted(timestamps)


async def test_duration_is_none_for_a_task_with_fewer_than_two_events(
    db_session: AsyncSession,
) -> None:
    from acr.core.tasks.models import Task

    task = Task(objective="constructed directly, no telemetry")
    db_session.add(task)
    await db_session.flush()

    explanation = await explain_task(db_session, task.id)

    assert explanation.events == []
    assert explanation.duration_seconds is None
