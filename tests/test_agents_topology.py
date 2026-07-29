"""Tests for acr.agents.topology (master §774-793)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.topology import recommend_topology, record_topology


async def test_recommend_topology_returns_none_below_min_samples(
    db_session: AsyncSession,
) -> None:
    for _ in range(2):
        await record_topology(
            db_session, task_class="research", worker_count=1, model_names=["mock"], skill_ids=[]
        )

    recommendation = await recommend_topology(db_session, "research", min_samples=3)

    assert recommendation is None


async def test_recommend_topology_returns_none_for_low_success_rate(
    db_session: AsyncSession,
) -> None:
    for succeeded in (True, False, False, False):
        await record_topology(
            db_session,
            task_class="research",
            worker_count=1,
            model_names=["mock"],
            skill_ids=[],
            succeeded=succeeded,
        )

    recommendation = await recommend_topology(
        db_session, "research", min_samples=3, min_success_rate=0.6
    )

    assert recommendation is None


async def test_recommend_topology_recommends_with_enough_evidence(
    db_session: AsyncSession,
) -> None:
    for worker_count, quality in ((1, 0.8), (1, 0.9), (2, 0.7)):
        await record_topology(
            db_session,
            task_class="research",
            worker_count=worker_count,
            model_names=["mock"],
            skill_ids=["skill-a"],
            quality_score=quality,
            succeeded=True,
        )

    recommendation = await recommend_topology(db_session, "research", min_samples=3)

    assert recommendation is not None
    assert recommendation.sample_count == 3
    assert recommendation.success_rate == 1.0
    # worker counts (1, 1, 2) -> round(4 / 3) == 1, deterministically -- not
    # a range guess.
    assert recommendation.recommended_worker_count == 1
    assert recommendation.mean_quality_score > 0


async def test_recommend_topology_only_considers_the_matching_task_class(
    db_session: AsyncSession,
) -> None:
    for _ in range(3):
        await record_topology(
            db_session, task_class="research", worker_count=1, model_names=["mock"], skill_ids=[]
        )
    for _ in range(3):
        await record_topology(
            db_session, task_class="coding", worker_count=2, model_names=["mock"], skill_ids=[]
        )

    recommendation = await recommend_topology(db_session, "research", min_samples=3)

    assert recommendation is not None
    assert recommendation.recommended_worker_count == 1
