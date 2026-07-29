"""Tests for acr.learning.proposals (master §1721-1727, controlled self-improvement)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.config import Settings
from acr.learning.proposals import (
    ProposalKind,
    ProposalNotFoundError,
    ProposalNotPendingError,
    ProposalStatus,
    SelfImprovementDisabledError,
    approve_proposal,
    list_proposals,
    propose_routing_optimization,
    propose_skill_evolution,
    reject_proposal,
)
from acr.learning.routing_optimization import ModelOutcome
from acr.security.audit import recent_audit_events
from acr.skills.evolution import create_candidate_version
from acr.skills.models import SkillStatus
from acr.skills.registry import SkillNotFoundError, get, register, set_status
from acr.telemetry.recorder import TelemetryRecorder

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


async def _seed_improving_candidate(db_session: AsyncSession, tmp_path: Path) -> tuple[str, str]:
    baseline = await register(db_session, FIXTURES / "sqlite-diagnostics")
    baseline = await set_status(db_session, baseline.id, SkillStatus.ACTIVE)
    candidate = await create_candidate_version(db_session, tmp_path, baseline, {})
    await db_session.commit()
    return baseline.id, candidate.id


async def _seed_regressing_candidate(db_session: AsyncSession, tmp_path: Path) -> tuple[str, str]:
    baseline = await register(db_session, FIXTURES / "sqlite-diagnostics")
    baseline = await set_status(db_session, baseline.id, SkillStatus.ACTIVE)
    candidate = await create_candidate_version(
        db_session, tmp_path, baseline, {"token_estimate": 999_999}
    )
    await db_session.commit()
    return baseline.id, candidate.id


async def test_propose_skill_evolution_creates_a_pending_proposal_when_recommended(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline_id, candidate_id = await _seed_improving_candidate(db_session, tmp_path)

    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline_id,
        candidate_id=candidate_id,
    )
    await db_session.commit()

    assert proposal is not None
    assert proposal.status is ProposalStatus.PENDING
    assert proposal.subject == baseline_id
    assert proposal.payload["candidate_id"] == candidate_id


async def test_propose_skill_evolution_returns_none_for_a_regression(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline_id, candidate_id = await _seed_regressing_candidate(db_session, tmp_path)

    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline_id,
        candidate_id=candidate_id,
    )

    assert proposal is None
    assert await list_proposals(db_session) == []


async def test_propose_skill_evolution_raises_when_self_improvement_disabled(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline_id, candidate_id = await _seed_improving_candidate(db_session, tmp_path)
    migrated_settings.self_improvement_enabled = False

    with pytest.raises(SelfImprovementDisabledError):
        await propose_skill_evolution(
            db_session,
            migrated_settings,
            TelemetryRecorder(),
            baseline_id=baseline_id,
            candidate_id=candidate_id,
        )


async def test_propose_skill_evolution_raises_for_unknown_skill(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    with pytest.raises(SkillNotFoundError):
        await propose_skill_evolution(
            db_session,
            migrated_settings,
            TelemetryRecorder(),
            baseline_id="does-not-exist",
            candidate_id="also-does-not-exist",
        )


async def test_propose_skill_evolution_auto_applies_when_configured(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline_id, candidate_id = await _seed_improving_candidate(db_session, tmp_path)
    migrated_settings.auto_apply_proposals = True

    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline_id,
        candidate_id=candidate_id,
    )
    await db_session.commit()

    assert proposal is not None
    assert proposal.status is ProposalStatus.AUTO_APPLIED
    candidate = await get(db_session, candidate_id)
    assert candidate is not None
    assert candidate.status is SkillStatus.ACTIVE


async def test_approve_proposal_applies_the_promotion(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline_id, candidate_id = await _seed_improving_candidate(db_session, tmp_path)
    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline_id,
        candidate_id=candidate_id,
    )
    await db_session.commit()
    assert proposal is not None

    approved = await approve_proposal(db_session, TelemetryRecorder(), proposal.id)
    await db_session.commit()

    assert approved.status is ProposalStatus.APPROVED
    candidate = await get(db_session, candidate_id)
    assert candidate is not None
    assert candidate.status is SkillStatus.ACTIVE
    baseline = await get(db_session, baseline_id)
    assert baseline is not None
    assert baseline.status is SkillStatus.DEPRECATED


async def test_reject_proposal_does_not_apply_anything(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline_id, candidate_id = await _seed_improving_candidate(db_session, tmp_path)
    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline_id,
        candidate_id=candidate_id,
    )
    await db_session.commit()
    assert proposal is not None

    rejected = await reject_proposal(db_session, TelemetryRecorder(), proposal.id)
    await db_session.commit()

    assert rejected.status is ProposalStatus.REJECTED
    candidate = await get(db_session, candidate_id)
    assert candidate is not None
    assert candidate.status is SkillStatus.EXPERIMENTAL


async def test_approve_proposal_raises_for_unknown_id(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(ProposalNotFoundError):
        await approve_proposal(db_session, TelemetryRecorder(), "does-not-exist")


async def test_approve_proposal_raises_when_already_decided(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline_id, candidate_id = await _seed_improving_candidate(db_session, tmp_path)
    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline_id,
        candidate_id=candidate_id,
    )
    await db_session.commit()
    assert proposal is not None
    await reject_proposal(db_session, TelemetryRecorder(), proposal.id)
    await db_session.commit()

    with pytest.raises(ProposalNotPendingError):
        await approve_proposal(db_session, TelemetryRecorder(), proposal.id)


async def test_list_proposals_filters_by_status(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline_id, candidate_id = await _seed_improving_candidate(db_session, tmp_path)
    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline_id,
        candidate_id=candidate_id,
    )
    await db_session.commit()
    assert proposal is not None

    pending = await list_proposals(db_session, status=ProposalStatus.PENDING)
    approved = await list_proposals(db_session, status=ProposalStatus.APPROVED)

    assert [p.id for p in pending] == [proposal.id]
    assert approved == []


async def test_propose_routing_optimization_creates_a_pending_proposal_when_recommended(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    current = ModelOutcome(model_name="mock", samples=5, success_rate=0.6, mean_quality=0.5)
    candidate = ModelOutcome(model_name="ollama", samples=5, success_rate=0.9, mean_quality=0.8)

    proposal = await propose_routing_optimization(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        task_class="ui-audit",
        current=current,
        candidate=candidate,
    )
    await db_session.commit()

    assert proposal is not None
    assert proposal.kind is ProposalKind.ROUTING_OPTIMIZATION
    assert proposal.status is ProposalStatus.PENDING
    assert proposal.subject == "ui-audit"


async def test_propose_routing_optimization_returns_none_without_clear_improvement(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    current = ModelOutcome(model_name="mock", samples=5, success_rate=0.8, mean_quality=0.8)
    candidate = ModelOutcome(model_name="ollama", samples=5, success_rate=0.8, mean_quality=0.8)

    proposal = await propose_routing_optimization(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        task_class="ui-audit",
        current=current,
        candidate=candidate,
    )

    assert proposal is None


async def test_propose_routing_optimization_never_auto_applies_even_when_configured(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    migrated_settings.auto_apply_proposals = True
    current = ModelOutcome(model_name="mock", samples=5, success_rate=0.6, mean_quality=0.5)
    candidate = ModelOutcome(model_name="ollama", samples=5, success_rate=0.9, mean_quality=0.8)

    proposal = await propose_routing_optimization(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        task_class="ui-audit",
        current=current,
        candidate=candidate,
    )
    await db_session.commit()

    # Unlike skill evolution, there is no safe mechanism to auto-apply a
    # routing change -- this must stay PENDING regardless of the setting.
    assert proposal is not None
    assert proposal.status is ProposalStatus.PENDING


async def test_approving_a_routing_optimization_proposal_mutates_nothing_but_its_own_status(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    current = ModelOutcome(model_name="mock", samples=5, success_rate=0.6, mean_quality=0.5)
    candidate = ModelOutcome(model_name="ollama", samples=5, success_rate=0.9, mean_quality=0.8)
    proposal = await propose_routing_optimization(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        task_class="ui-audit",
        current=current,
        candidate=candidate,
    )
    await db_session.commit()
    assert proposal is not None

    approved = await approve_proposal(db_session, TelemetryRecorder(), proposal.id)
    await db_session.commit()

    assert approved.status is ProposalStatus.APPROVED


async def test_propose_routing_optimization_raises_when_self_improvement_disabled(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    migrated_settings.self_improvement_enabled = False
    current = ModelOutcome(model_name="mock", samples=5, success_rate=0.6, mean_quality=0.5)
    candidate = ModelOutcome(model_name="ollama", samples=5, success_rate=0.9, mean_quality=0.8)

    with pytest.raises(SelfImprovementDisabledError):
        await propose_routing_optimization(
            db_session,
            migrated_settings,
            TelemetryRecorder(),
            task_class="ui-audit",
            current=current,
            candidate=candidate,
        )


async def test_propose_and_approve_are_audit_logged(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline_id, candidate_id = await _seed_improving_candidate(db_session, tmp_path)
    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline_id,
        candidate_id=candidate_id,
    )
    await db_session.commit()
    assert proposal is not None
    await approve_proposal(db_session, TelemetryRecorder(), proposal.id)
    await db_session.commit()

    events = await recent_audit_events(db_session)
    actions = {e.payload.get("action") for e in events}
    assert f"proposal.create:{proposal.id}" in actions
    assert f"proposal.approve:{proposal.id}" in actions
