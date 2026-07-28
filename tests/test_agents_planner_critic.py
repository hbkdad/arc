"""Tests for acr.agents.planner and acr.agents.critic (master §747-772)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.critic import review_agent_task
from acr.agents.planner import plan_agent
from acr.core.execution import run_task
from acr.core.tasks.models import Task, TaskStatus
from acr.providers.mock import MockProvider
from acr.skills.models import SkillStatus
from acr.skills.registry import register, set_status
from acr.telemetry.recorder import TelemetryRecorder

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


async def test_plan_agent_grants_no_skills_or_tools_for_an_unrelated_objective(
    db_session: AsyncSession,
) -> None:
    spec = await plan_agent(db_session, "compile a container image")

    assert spec.objective == "compile a container image"
    assert spec.skills == []
    assert spec.tools == []
    assert spec.id.startswith("agent-")


async def test_plan_agent_grants_relevant_active_skill_and_tool(
    db_session: AsyncSession,
) -> None:
    record = await register(db_session, FIXTURES / "sqlite-diagnostics")
    await set_status(db_session, record.id, SkillStatus.ACTIVE)

    spec = await plan_agent(db_session, "diagnose a corrupted SQLite database")

    assert record.id in spec.skills


def test_review_agent_task_passes_for_a_completed_task() -> None:
    # Constructed directly rather than run through the engine — critic
    # review only needs a Task object with a final status.
    task = Task(objective="say hello", status=TaskStatus.COMPLETED)

    result = review_agent_task(task)

    assert result.passed is True


def test_review_agent_task_fails_for_a_failed_task() -> None:
    task = Task(objective="say hello", status=TaskStatus.FAILED)

    result = review_agent_task(task)

    assert result.passed is False


async def test_review_agent_task_on_a_real_completed_run(db_session: AsyncSession) -> None:
    task = await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    result = review_agent_task(task)

    assert result.passed is True
    assert result.mean_score == 1.0
