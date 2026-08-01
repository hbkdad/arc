"""Tests for acr.agents.factory and acr.agents.models (master §747-772)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.factory import (
    SpawnNotWorthwhileError,
    estimate_spawn,
    spawn_agent,
    spawn_agent_with_escalation,
)
from acr.agents.models import AgentSpec
from acr.agents.topology import AgentTopologyRecord
from acr.core.tasks.models import TaskStatus
from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider
from acr.providers.mock import MockProvider
from acr.routing.models import ModelProfile, ModelRouter, NoProviderAvailableError
from acr.skills.models import SkillStatus
from acr.skills.registry import get as get_skill
from acr.skills.registry import register, set_status
from acr.telemetry.recorder import TelemetryRecorder

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


class _AlwaysFailsProvider(ModelProvider):
    name = "always-fails"

    async def is_available(self) -> bool:
        return True

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        raise RuntimeError("simulated provider failure")


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

    task, review = await spawn_agent(
        db_session, spec, MockProvider(), TelemetryRecorder(), task_class="greeting"
    )

    assert task.status is TaskStatus.COMPLETED
    assert task.objective == "say hello"
    assert review.passed is True


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
        await spawn_agent(
            db_session, spec, MockProvider(), TelemetryRecorder(), task_class="greeting"
        )


async def test_spawn_agent_runs_an_overloaded_spec_when_forced(
    db_session: AsyncSession,
) -> None:
    spec = _spec(
        objective="say hello",
        tools=[f"tool-{i}" for i in range(20)],
        permissions=[f"perm-{i}" for i in range(20)],
    )

    task, _review = await spawn_agent(
        db_session, spec, MockProvider(), TelemetryRecorder(), task_class="greeting", force=True
    )

    assert task.status is TaskStatus.COMPLETED


async def test_spawn_agent_records_topology_for_the_run(db_session: AsyncSession) -> None:
    # This is the real gap fixed here: record_topology() existed since
    # Phase 10 but nothing in application code ever called it, so
    # recommend_topology() could never see evidence no matter how many
    # agents actually ran.
    spec = _spec(objective="say hello", tools=["memory_search"])

    await spawn_agent(db_session, spec, MockProvider(), TelemetryRecorder(), task_class="greeting")

    rows = (
        (
            await db_session.execute(
                select(AgentTopologyRecord).where(AgentTopologyRecord.task_class == "greeting")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].succeeded is True
    assert rows[0].worker_count == 1
    assert rows[0].model_names == ["mock"]


async def test_spawn_agent_records_a_successful_outcome_for_each_routed_skill(
    db_session: AsyncSession,
) -> None:
    # Same gap, the skill-reliability half: record_skill_outcome() existed
    # since Phase 8 but was likewise never called from a real code path.
    skill = await register(db_session, FIXTURES / "sqlite-diagnostics")
    await set_status(db_session, skill.id, SkillStatus.ACTIVE)
    spec = _spec(objective="say hello", skills=[skill.id])

    await spawn_agent(db_session, spec, MockProvider(), TelemetryRecorder(), task_class="greeting")

    updated = await get_skill(db_session, skill.id)
    assert updated is not None
    assert updated.successful_uses == 1
    assert updated.failed_uses == 0
    assert updated.reliability == 1.0


async def test_spawn_agent_records_a_failed_outcome_when_the_task_fails(
    db_session: AsyncSession,
) -> None:
    skill = await register(db_session, FIXTURES / "sqlite-diagnostics")
    await set_status(db_session, skill.id, SkillStatus.ACTIVE)
    spec = _spec(objective="say hello", skills=[skill.id])

    task, review = await spawn_agent(
        db_session, spec, _AlwaysFailsProvider(), TelemetryRecorder(), task_class="greeting"
    )

    assert task.status is TaskStatus.FAILED
    assert review.passed is False
    updated = await get_skill(db_session, skill.id)
    assert updated is not None
    assert updated.failed_uses == 1
    assert updated.reliability == 0.0


def _escalation_router() -> ModelRouter:
    return ModelRouter(
        [
            ModelProfile(
                provider=_AlwaysFailsProvider(),
                name="cheap-tier",
                cost_per_1k_tokens=0.0,
                quality_tier=0,
            ),
            ModelProfile(
                provider=MockProvider(), name="pricey-tier", cost_per_1k_tokens=0.5, quality_tier=1
            ),
        ]
    )


async def test_spawn_agent_with_escalation_succeeds_on_the_cheap_tier_without_escalating(
    db_session: AsyncSession,
) -> None:
    spec = _spec(objective="say hello")
    router = ModelRouter(
        [ModelProfile(provider=MockProvider(), name="mock", cost_per_1k_tokens=0.0, quality_tier=0)]
    )

    task, review = await spawn_agent_with_escalation(
        db_session, spec, router, TelemetryRecorder(), task_class="greeting"
    )

    assert task.status is TaskStatus.COMPLETED
    assert review.passed is True
    rows = (
        (
            await db_session.execute(
                select(AgentTopologyRecord).where(AgentTopologyRecord.task_class == "greeting")
            )
        )
        .scalars()
        .all()
    )
    assert rows[0].model_names == ["mock"]


async def test_spawn_agent_with_escalation_escalates_when_the_cheap_tier_fails_review(
    db_session: AsyncSession,
) -> None:
    spec = _spec(objective="say hello")

    task, review = await spawn_agent_with_escalation(
        db_session, spec, _escalation_router(), TelemetryRecorder(), task_class="greeting"
    )

    assert task.status is TaskStatus.COMPLETED
    assert review.passed is True
    rows = (
        (
            await db_session.execute(
                select(AgentTopologyRecord).where(AgentTopologyRecord.task_class == "greeting")
            )
        )
        .scalars()
        .all()
    )
    # Both tiers show up honestly -- the failed cheap attempt is never hidden.
    assert rows[0].model_names == ["cheap-tier", "pricey-tier"]


async def test_spawn_agent_with_escalation_returns_the_last_attempt_if_every_tier_fails(
    db_session: AsyncSession,
) -> None:
    spec = _spec(objective="say hello")
    router = ModelRouter(
        [
            ModelProfile(
                provider=_AlwaysFailsProvider(),
                name="only-tier",
                cost_per_1k_tokens=0.0,
                quality_tier=0,
            )
        ]
    )

    task, review = await spawn_agent_with_escalation(
        db_session, spec, router, TelemetryRecorder(), task_class="greeting"
    )

    assert task.status is TaskStatus.FAILED
    assert review.passed is False


async def test_spawn_agent_with_escalation_respects_min_quality_tier(
    db_session: AsyncSession,
) -> None:
    spec = _spec(objective="say hello")

    task, review = await spawn_agent_with_escalation(
        db_session,
        spec,
        _escalation_router(),
        TelemetryRecorder(),
        task_class="greeting",
        min_quality_tier=1,
    )

    assert task.status is TaskStatus.COMPLETED
    assert review.passed is True


async def test_spawn_agent_with_escalation_raises_if_no_tier_meets_the_minimum(
    db_session: AsyncSession,
) -> None:
    spec = _spec(objective="say hello")

    with pytest.raises(NoProviderAvailableError):
        await spawn_agent_with_escalation(
            db_session,
            spec,
            _escalation_router(),
            TelemetryRecorder(),
            task_class="greeting",
            min_quality_tier=5,
        )


async def test_spawn_agent_with_escalation_refuses_an_overloaded_spec_without_force(
    db_session: AsyncSession,
) -> None:
    spec = _spec(
        objective="say hello",
        tools=[f"tool-{i}" for i in range(20)],
        permissions=[f"perm-{i}" for i in range(20)],
    )

    with pytest.raises(SpawnNotWorthwhileError):
        await spawn_agent_with_escalation(
            db_session, spec, _escalation_router(), TelemetryRecorder(), task_class="greeting"
        )
