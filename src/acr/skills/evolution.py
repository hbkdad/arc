"""Skill evolution (master §733-746).

"Never mutate active skills invisibly." Evolving `skill_id` creates a new,
separately versioned candidate (`<skill_id>@v<n>`) rather than editing the
active skill's package in place — both versions coexist as distinct
registry rows. The candidate is compared against its baseline and only
promoted on the caller's explicit decision (`promote_evolution`); the
baseline is never deleted, so `rollback_evolution` is just reactivating it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from acr.skills.format import load_manifest
from acr.skills.models import SkillRecord, SkillStatus
from acr.skills.registry import register, set_status

_VERSION_SUFFIX = re.compile(r"@v(\d+)$")


def _base_id(skill_id: str) -> str:
    return _VERSION_SUFFIX.sub("", skill_id)


def _next_candidate_id(base_skill: SkillRecord) -> str:
    base = _base_id(base_skill.id)
    match = _VERSION_SUFFIX.search(base_skill.id)
    current_version = int(match.group(1)) if match else 1
    return f"{base}@v{current_version + 1}"


async def create_candidate_version(
    session: AsyncSession,
    data_dir: Path,
    base_skill: SkillRecord,
    overrides: dict[str, Any],
) -> SkillRecord:
    """Write a new SKILL.yaml versioned off `base_skill`, applying `overrides`
    on top of its current manifest. Registers as EXPERIMENTAL — an evolution
    candidate is reviewed the same as any newly authored skill, not
    auto-quarantined the way a freshly *generated* one is (master §704 is
    about generation, not evolution)."""
    base_manifest = load_manifest(Path(base_skill.path))
    candidate_id = _next_candidate_id(base_skill)

    manifest = base_manifest.model_dump()
    manifest.update(overrides)
    manifest["id"] = candidate_id
    manifest["origin"] = "evolved"

    candidate_dir = data_dir / "generated_skills" / candidate_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "SKILL.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )

    return await register(session, candidate_dir)


@dataclass(frozen=True, slots=True)
class EvolutionComparison:
    baseline_id: str
    candidate_id: str
    baseline_reliability: float
    candidate_reliability: float
    baseline_token_estimate: int
    candidate_token_estimate: int
    recommend_promote: bool
    reason: str


def compare_versions(baseline: SkillRecord, candidate: SkillRecord) -> EvolutionComparison:
    """Master §738-744's quality/tokens/latency/cost dimensions, reduced to
    what ACR can measure without real usage data: `reliability` (a quality
    proxy already tracked by Phase 8's utility updates) and `token_estimate`
    (a cost/latency proxy). Security is `acr.skills.validation`'s job — a
    candidate that fails validation should never reach comparison.
    """
    quality_regressed = candidate.reliability < baseline.reliability
    cost_regressed = candidate.token_estimate > baseline.token_estimate

    if quality_regressed and cost_regressed:
        reason = "candidate is both less reliable and more expensive than baseline"
    elif quality_regressed:
        reason = "candidate is less reliable than baseline"
    elif cost_regressed:
        reason = "candidate costs more tokens than baseline"
    else:
        reason = "candidate matches or improves on baseline reliability and cost"

    return EvolutionComparison(
        baseline_id=baseline.id,
        candidate_id=candidate.id,
        baseline_reliability=baseline.reliability,
        candidate_reliability=candidate.reliability,
        baseline_token_estimate=baseline.token_estimate,
        candidate_token_estimate=candidate.token_estimate,
        recommend_promote=not (quality_regressed or cost_regressed),
        reason=reason,
    )


async def promote_evolution(
    session: AsyncSession, baseline: SkillRecord, candidate_id: str, *, safe_mode: bool = False
) -> SkillRecord:
    """Deprecate `baseline` (if currently active) and activate `candidate_id`."""
    if baseline.status is SkillStatus.ACTIVE:
        await set_status(session, baseline.id, SkillStatus.DEPRECATED, safe_mode=safe_mode)
    return await set_status(session, candidate_id, SkillStatus.ACTIVE, safe_mode=safe_mode)


async def rollback_evolution(
    session: AsyncSession, *, active_id: str, restore_id: str, safe_mode: bool = False
) -> SkillRecord:
    """Deprecate the currently active `active_id` and reactivate `restore_id`."""
    await set_status(session, active_id, SkillStatus.DEPRECATED, safe_mode=safe_mode)
    return await set_status(session, restore_id, SkillStatus.ACTIVE, safe_mode=safe_mode)
