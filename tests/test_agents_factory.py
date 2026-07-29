"""Tests for acr.agents.factory and acr.agents.models (master §747-772)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.factory import SpawnNotWorthwhileError, estimate_spawn, spawn_agent
from acr.agents.models import AgentSpec
from acr.core.tasks.models import TaskStatus
from acr.providers.mock import MockProvider
from acr.telemetry.recorder import TelemetryRecorder


def _spec(**overrides: object) -> AgentSpec:
    defaults: dict[str, object] = dict(
        id="agent-1", role="worker", objective="say hello", scope="task"
    )
    defaults.update(overrides)
    return AgentSpec(**defaults)  # type: ignore[arg-type]


def test_estimate_spawn_favors_a_scoped_spec_over_an_unscoped_one() -> None:
    unscoped = estimate_spawn(_spec())
    scoped = estimate_spawn(_spec(tools=["memory_search"], skills=["sqlite-diagnostics"]))

    assert scoped.expected_quality_gain > unscoped.expected_quality_gain


def test_estimate_spawn_overhead_and_risk_grow_with_grants() -> None:
    minimal = estimate_spawn(_spec())
    heavy = estimate_spawn(
        _spec(
            tools=["a", "b", "c"],
            skills=["d", "e"],
            permissions=["memory.read", "memory.write"],
        )
    )

    assert heavy.coordination_overhead > minimal.coordination_overhead
    assert heavy.security_risk > minimal.security_risk


def test_worth_spawning_is_true_when_quality_gain_clears_costs() -> None:
    estimate = estimate_spawn(_spec(tools=["memory_search"]))
    assert estimate.worth_spawning is True


def test_worth_spawning_is_false_for_an_overloaded_spec() -> None:
    estimate = estimate_spawn(
        _spec(
            tools=[f"tool-{i}" for i in range(20)],
            permissions=[f"perm-{i}" for i in range(20)],
        )
    )
    assert estimate.worth_spawning is False


async def test_spawn_agent_runs_the_objective_through_the_task_engine(
    db_session: AsyncSession,
) -> None:
    spec = _spec(objective="say hello")

    task = await spawn_agent(db_session, spec, MockProvider(), TelemetryRecorder())

    assert task.status is TaskStatus.COMPLETED
    assert task.objective == "say hello"


async def test_spawn_agent_refuses_an_overloaded_spec_without_force(
    db_session: AsyncSession,
) -> None:
    # The cost/risk gate must be enforced by spawn_agent() itself, not only
    # by the CLI command that happens to be its one caller today -- any
    # future caller (MCP exposure, planner auto-run) must not be able to
    # silently bypass it just by calling this function directly.
    spec = _spec(
        objective="say hello",
        tools=[f"tool-{i}" for i in range(20)],
        permissions=[f"perm-{i}" for i in range(20)],
    )

    with pytest.raises(SpawnNotWorthwhileError):
        await spawn_agent(db_session, spec, MockProvider(), TelemetryRecorder())


async def test_spawn_agent_runs_an_overloaded_spec_when_forced(
    db_session: AsyncSession,
) -> None:
    spec = _spec(
        objective="say hello",
        tools=[f"tool-{i}" for i in range(20)],
        permissions=[f"perm-{i}" for i in range(20)],
    )

    task = await spawn_agent(db_session, spec, MockProvider(), TelemetryRecorder(), force=True)

    assert task.status is TaskStatus.COMPLETED
