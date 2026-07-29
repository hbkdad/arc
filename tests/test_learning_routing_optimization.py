"""Tests for acr.learning.routing_optimization."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.topology import record_topology
from acr.learning.routing_optimization import compare_models, model_outcomes_for_task_class


async def _seed(
    session: AsyncSession, *, model: str, succeeded: bool, quality: float, count: int
) -> None:
    for _ in range(count):
        await record_topology(
            session,
            task_class="ui-audit",
            worker_count=1,
            model_names=[model],
            skill_ids=[],
            quality_score=quality,
            succeeded=succeeded,
        )
    await session.commit()


async def test_a_model_below_min_samples_is_excluded(db_session: AsyncSession) -> None:
    await _seed(db_session, model="mock", succeeded=True, quality=1.0, count=2)

    outcomes = await model_outcomes_for_task_class(db_session, task_class="ui-audit", min_samples=3)

    assert outcomes == []


async def test_a_model_at_min_samples_is_included_with_real_numbers(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, model="mock", succeeded=True, quality=0.8, count=3)

    outcomes = await model_outcomes_for_task_class(db_session, task_class="ui-audit", min_samples=3)

    assert len(outcomes) == 1
    assert outcomes[0].model_name == "mock"
    assert outcomes[0].samples == 3
    assert outcomes[0].success_rate == 1.0
    assert outcomes[0].mean_quality == pytest.approx(0.8)


async def test_outcomes_are_scoped_to_the_requested_task_class(db_session: AsyncSession) -> None:
    await _seed(db_session, model="mock", succeeded=True, quality=1.0, count=3)
    for _ in range(3):
        await record_topology(
            db_session,
            task_class="code-review",
            worker_count=1,
            model_names=["mock"],
            skill_ids=[],
            quality_score=1.0,
            succeeded=True,
        )
    await db_session.commit()

    outcomes = await model_outcomes_for_task_class(db_session, task_class="ui-audit", min_samples=3)

    assert len(outcomes) == 1


def test_compare_models_recommends_a_switch_when_candidate_wins_on_both_dimensions() -> None:
    current = _outcome("mock", success_rate=0.6, mean_quality=0.5)
    candidate = _outcome("ollama", success_rate=0.9, mean_quality=0.8)

    comparison = compare_models(current, candidate, task_class="ui-audit")

    assert comparison.recommend_switch is True
    assert "ollama" in comparison.reason
    assert "mock" in comparison.reason


def test_compare_models_does_not_recommend_when_only_one_dimension_improves() -> None:
    current = _outcome("mock", success_rate=0.6, mean_quality=0.5)
    candidate = _outcome("ollama", success_rate=0.9, mean_quality=0.4)  # quality regressed

    comparison = compare_models(current, candidate, task_class="ui-audit")

    assert comparison.recommend_switch is False


def test_compare_models_does_not_recommend_a_tie() -> None:
    current = _outcome("mock", success_rate=0.8, mean_quality=0.8)
    candidate = _outcome("ollama", success_rate=0.8, mean_quality=0.8)

    comparison = compare_models(current, candidate, task_class="ui-audit")

    assert comparison.recommend_switch is False


def _outcome(name: str, *, success_rate: float, mean_quality: float):
    from acr.learning.routing_optimization import ModelOutcome

    return ModelOutcome(
        model_name=name, samples=5, success_rate=success_rate, mean_quality=mean_quality
    )
