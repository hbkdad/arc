"""Tests for acr.skills.evolution (master §733-746)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.security.safe_mode import SafeModeError
from acr.skills.evolution import (
    compare_versions,
    create_candidate_version,
    promote_evolution,
    rollback_evolution,
)
from acr.skills.models import SkillRecord, SkillStatus
from acr.skills.registry import register, set_status

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


async def test_create_candidate_version_writes_a_new_versioned_package(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline = await register(db_session, FIXTURES / "sqlite-diagnostics")

    candidate = await create_candidate_version(
        db_session, tmp_path, baseline, {"description": "An improved diagnostics skill."}
    )

    assert candidate.id == "sqlite-diagnostics@v2"
    assert candidate.status is SkillStatus.EXPERIMENTAL
    assert candidate.description == "An improved diagnostics skill."
    assert candidate.origin == "evolved"
    assert (tmp_path / "generated_skills" / candidate.id / "SKILL.yaml").is_file()


async def test_create_candidate_version_increments_across_repeated_evolution(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline = await register(db_session, FIXTURES / "sqlite-diagnostics")
    v2 = await create_candidate_version(db_session, tmp_path, baseline, {})
    v3 = await create_candidate_version(db_session, tmp_path, v2, {})

    assert v2.id == "sqlite-diagnostics@v2"
    assert v3.id == "sqlite-diagnostics@v3"


def _record_like(**overrides: object) -> SkillRecord:
    defaults: dict[str, object] = dict(
        id="s",
        name="s",
        version="1.0.0",
        description="d",
        path="/tmp/s",
        reliability=0.5,
        token_estimate=100,
        status=SkillStatus.ACTIVE,
    )
    defaults.update(overrides)
    return SkillRecord(**defaults)  # type: ignore[arg-type]


def test_compare_versions_recommends_promotion_when_candidate_improves() -> None:
    baseline = _record_like(id="base", reliability=0.5, token_estimate=100)
    candidate = _record_like(id="cand", reliability=0.8, token_estimate=90)

    comparison = compare_versions(baseline, candidate)

    assert comparison.recommend_promote is True
    assert "improves" in comparison.reason


def test_compare_versions_rejects_a_less_reliable_candidate() -> None:
    baseline = _record_like(id="base", reliability=0.8, token_estimate=100)
    candidate = _record_like(id="cand", reliability=0.3, token_estimate=100)

    comparison = compare_versions(baseline, candidate)

    assert comparison.recommend_promote is False
    assert "less reliable" in comparison.reason


def test_compare_versions_rejects_a_more_expensive_candidate() -> None:
    baseline = _record_like(id="base", reliability=0.5, token_estimate=100)
    candidate = _record_like(id="cand", reliability=0.5, token_estimate=200)

    comparison = compare_versions(baseline, candidate)

    assert comparison.recommend_promote is False
    assert "more tokens" in comparison.reason


async def test_promote_evolution_deprecates_active_baseline_and_activates_candidate(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline = await register(db_session, FIXTURES / "sqlite-diagnostics")
    baseline = await set_status(db_session, baseline.id, SkillStatus.ACTIVE)
    candidate = await create_candidate_version(db_session, tmp_path, baseline, {})

    promoted = await promote_evolution(db_session, baseline, candidate.id)

    assert promoted.status is SkillStatus.ACTIVE
    refreshed_baseline = await db_session.get(type(baseline), baseline.id)
    assert refreshed_baseline is not None
    assert refreshed_baseline.status is SkillStatus.DEPRECATED


async def test_promote_evolution_skips_deprecation_when_baseline_not_active(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline = await register(db_session, FIXTURES / "sqlite-diagnostics")  # stays EXPERIMENTAL
    candidate = await create_candidate_version(db_session, tmp_path, baseline, {})

    promoted = await promote_evolution(db_session, baseline, candidate.id)

    assert promoted.status is SkillStatus.ACTIVE
    refreshed_baseline = await db_session.get(type(baseline), baseline.id)
    assert refreshed_baseline is not None
    assert refreshed_baseline.status is SkillStatus.EXPERIMENTAL


async def test_rollback_evolution_restores_a_prior_version(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline = await register(db_session, FIXTURES / "sqlite-diagnostics")
    baseline = await set_status(db_session, baseline.id, SkillStatus.ACTIVE)
    candidate = await create_candidate_version(db_session, tmp_path, baseline, {})
    await promote_evolution(db_session, baseline, candidate.id)

    restored = await rollback_evolution(db_session, active_id=candidate.id, restore_id=baseline.id)

    assert restored.id == baseline.id
    assert restored.status is SkillStatus.ACTIVE
    refreshed_candidate = await db_session.get(type(candidate), candidate.id)
    assert refreshed_candidate is not None
    assert refreshed_candidate.status is SkillStatus.DEPRECATED


async def test_promote_evolution_respects_safe_mode(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline = await register(db_session, FIXTURES / "sqlite-diagnostics")
    baseline = await set_status(db_session, baseline.id, SkillStatus.ACTIVE)
    candidate = await create_candidate_version(db_session, tmp_path, baseline, {})

    with pytest.raises(SafeModeError):
        await promote_evolution(db_session, baseline, candidate.id, safe_mode=True)
