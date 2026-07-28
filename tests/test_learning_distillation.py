"""Tests for acr.learning.distillation (master §631-644)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.execution import run_task
from acr.core.tasks.models import TaskStatus
from acr.learning.distillation import TaskNotFoundError, distill_and_remember, distill_task
from acr.memory.models import MemoryRecord, MemoryStatus, MemoryType
from acr.memory.write_controller import WriteDecision
from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider
from acr.providers.mock import MockProvider
from acr.telemetry.recorder import TelemetryRecorder


class _AlwaysFailsProvider(ModelProvider):
    name = "always-fails"

    async def is_available(self) -> bool:
        return True

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        raise RuntimeError("simulated provider failure")


async def test_distill_task_raises_for_unknown_task(db_session: AsyncSession) -> None:
    with pytest.raises(TaskNotFoundError):
        await distill_task(db_session, "does-not-exist")


async def test_distill_task_produces_a_memory_candidate_for_completed_task(
    db_session: AsyncSession,
) -> None:
    task = await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())
    assert task.status is TaskStatus.COMPLETED

    result = await distill_task(db_session, task.id)

    assert result.reason == "distilled"
    assert result.memory_candidate is not None
    assert result.memory_candidate.type is MemoryType.EPISODIC
    assert "say hello" in result.memory_candidate.content
    assert result.compression_ratio > 0


async def test_distill_task_skips_a_failed_task(db_session: AsyncSession) -> None:
    task = await run_task(db_session, "will fail", _AlwaysFailsProvider(), TelemetryRecorder())
    assert task.status is TaskStatus.FAILED

    result = await distill_task(db_session, task.id)

    assert result.memory_candidate is None
    assert "failed" in result.reason


async def test_distill_and_remember_stores_the_candidate(db_session: AsyncSession) -> None:
    task = await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    _result, evaluation = await distill_and_remember(db_session, task.id)
    await db_session.commit()

    assert evaluation is not None
    # confidence=0.7 with evidence -> STORE_CANDIDATE (below the 0.75 confirmation bar)
    assert evaluation.decision in (WriteDecision.STORE_CANDIDATE, WriteDecision.STORE_CONFIRMED)

    stored = (
        await db_session.execute(
            select(MemoryRecord).where(MemoryRecord.subject == f"task.{task.id}")
        )
    ).scalar_one()
    assert stored.status in (MemoryStatus.CANDIDATE, MemoryStatus.CONFIRMED)


async def test_distill_and_remember_returns_none_evaluation_for_failed_task(
    db_session: AsyncSession,
) -> None:
    task = await run_task(db_session, "will fail", _AlwaysFailsProvider(), TelemetryRecorder())

    result, evaluation = await distill_and_remember(db_session, task.id)

    assert evaluation is None
    assert result.memory_candidate is None
