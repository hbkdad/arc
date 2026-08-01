"""Tests for acr.learning.proposals (master §1721-1727, controlled self-improvement)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.config import Settings
from acr.learning.proposals import (
    MemoryRecordNotFoundError,
    ProposalKind,
    ProposalNotFoundError,
    ProposalNotPendingError,
    ProposalStatus,
    SelfImprovementDisabledError,
    approve_proposal,
    list_proposals,
    propose_memory_recalibration,
    propose_routing_optimization,
    propose_skill_evolution,
    reject_proposal,
)
from acr.learning.routing_optimization import ModelOutcome
from acr.memory import MemoryCandidate, MemoryScope, MemoryType
from acr.memory.models import MemoryRecord
from acr.memory.write_controller import remember
from acr.security.audit import recent_audit_events
from acr.security.safe_mode import SafeModeError
from acr.skills.evolution import create_candidate_version
from acr.skills.models import SkillStatus
from acr.skills.registry import SkillNotFoundError, get, register, set_status
from acr.skills.trajectory_audit import TrajectoryAuditResult, TrajectoryVerdict
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
    # No trajectory_audit passed -- the payload shape (and therefore
    # approve_proposal()'s later EvolutionComparison(**payload) call) must
    # stay exactly what it was before that parameter existed.
    assert "trajectory_audit" not in proposal.payload


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


def _audit(
    baseline_id: str, candidate_id: str, verdict: TrajectoryVerdict
) -> TrajectoryAuditResult:
    return TrajectoryAuditResult(
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        baseline_task_id="task-baseline",
        candidate_task_id="task-candidate",
        objective="check the tasks table",
        verdict=verdict,
        rationale="stub rationale for testing",
    )


async def test_propose_skill_evolution_with_a_favorable_audit_creates_a_proposal(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline_id, candidate_id = await _seed_improving_candidate(db_session, tmp_path)

    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        trajectory_audit=_audit(baseline_id, candidate_id, TrajectoryVerdict.CANDIDATE),
    )

    assert proposal is not None
    assert proposal.payload["trajectory_audit"]["verdict"] == "candidate"
    assert "trajectory audit also favors the candidate" in proposal.reason


async def test_approve_proposal_applies_a_trajectory_audited_proposal(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    # Regression test: the payload for an audited proposal carries an
    # extra "trajectory_audit" key alongside the plain comparison fields
    # (see the test above) -- approve_proposal()'s _apply() reconstructs
    # EvolutionComparison(**proposal.payload), which previously crashed
    # with an unexpected-keyword TypeError on that exact extra key. This
    # exercises the full propose -> approve -> promote path, not just
    # proposal creation.
    baseline_id, candidate_id = await _seed_improving_candidate(db_session, tmp_path)
    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        trajectory_audit=_audit(baseline_id, candidate_id, TrajectoryVerdict.CANDIDATE),
    )
    assert proposal is not None
    await db_session.commit()

    approved = await approve_proposal(db_session, TelemetryRecorder(), proposal.id)
    await db_session.commit()

    assert approved.status is ProposalStatus.APPROVED
    candidate = await get(db_session, candidate_id)
    assert candidate is not None
    assert candidate.status is SkillStatus.ACTIVE


async def test_propose_skill_evolution_with_a_tie_audit_returns_none_despite_numeric_win(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    # compare_versions() alone would recommend promotion here (same fixture
    # as the favorable-audit test above) -- a TIE verdict from the second,
    # independent signal must still block the proposal.
    baseline_id, candidate_id = await _seed_improving_candidate(db_session, tmp_path)

    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        trajectory_audit=_audit(baseline_id, candidate_id, TrajectoryVerdict.TIE),
    )

    assert proposal is None


async def test_propose_skill_evolution_with_a_baseline_favoring_audit_returns_none(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline_id, candidate_id = await _seed_improving_candidate(db_session, tmp_path)

    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        trajectory_audit=_audit(baseline_id, candidate_id, TrajectoryVerdict.BASELINE),
    )

    assert proposal is None


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


async def _seed_evidenced_memory(
    db_session: AsyncSession, *, confidence: float, successful_uses: int, failed_uses: int
) -> str:
    _evaluation, record = await remember(
        db_session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject="acr.recalibration.test",
            content="a memory record for recalibration testing",
            source_type="session",
            confidence=confidence,
            evidence="observed directly",
        ),
    )
    assert record is not None
    record.successful_uses = successful_uses
    record.failed_uses = failed_uses
    await db_session.flush()
    return record.id


async def test_propose_memory_recalibration_creates_a_pending_proposal_for_a_real_gap(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    # confidence 0.9, real empirical rate 1/5=0.2 -- a 0.7 gap.
    record_id = await _seed_evidenced_memory(
        db_session, confidence=0.9, successful_uses=1, failed_uses=4
    )

    proposal = await propose_memory_recalibration(
        db_session, migrated_settings, TelemetryRecorder(), record_id=record_id
    )
    await db_session.commit()

    assert proposal is not None
    assert proposal.kind is ProposalKind.MEMORY_RECALIBRATION
    assert proposal.status is ProposalStatus.PENDING
    assert proposal.payload["old_confidence"] == 0.9
    assert proposal.payload["new_confidence"] == 0.2


async def test_propose_memory_recalibration_returns_none_for_a_well_calibrated_record(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    record_id = await _seed_evidenced_memory(
        db_session, confidence=0.9, successful_uses=9, failed_uses=1
    )

    proposal = await propose_memory_recalibration(
        db_session, migrated_settings, TelemetryRecorder(), record_id=record_id
    )

    assert proposal is None


async def test_propose_memory_recalibration_returns_none_below_min_uses(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    record_id = await _seed_evidenced_memory(
        db_session, confidence=0.9, successful_uses=0, failed_uses=1
    )

    proposal = await propose_memory_recalibration(
        db_session, migrated_settings, TelemetryRecorder(), record_id=record_id, min_uses=3
    )

    assert proposal is None


async def test_propose_memory_recalibration_raises_for_an_unknown_record(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    with pytest.raises(MemoryRecordNotFoundError):
        await propose_memory_recalibration(
            db_session, migrated_settings, TelemetryRecorder(), record_id="does-not-exist"
        )


async def test_propose_memory_recalibration_raises_when_self_improvement_disabled(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    migrated_settings.self_improvement_enabled = False
    record_id = await _seed_evidenced_memory(
        db_session, confidence=0.9, successful_uses=1, failed_uses=4
    )

    with pytest.raises(SelfImprovementDisabledError):
        await propose_memory_recalibration(
            db_session, migrated_settings, TelemetryRecorder(), record_id=record_id
        )


async def test_propose_memory_recalibration_auto_applies_when_configured(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    migrated_settings.auto_apply_proposals = True
    record_id = await _seed_evidenced_memory(
        db_session, confidence=0.9, successful_uses=1, failed_uses=4
    )

    proposal = await propose_memory_recalibration(
        db_session, migrated_settings, TelemetryRecorder(), record_id=record_id
    )
    await db_session.commit()

    assert proposal is not None
    assert proposal.status is ProposalStatus.AUTO_APPLIED
    record = await db_session.get(MemoryRecord, record_id)
    assert record is not None
    assert record.confidence == pytest.approx(0.2)


async def test_propose_memory_recalibration_respects_safe_mode(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    migrated_settings.auto_apply_proposals = True
    migrated_settings.safe_mode = True
    record_id = await _seed_evidenced_memory(
        db_session, confidence=0.9, successful_uses=1, failed_uses=4
    )

    with pytest.raises(SafeModeError):
        await propose_memory_recalibration(
            db_session, migrated_settings, TelemetryRecorder(), record_id=record_id
        )


async def test_approving_a_recalibration_proposal_corrects_the_records_confidence(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    record_id = await _seed_evidenced_memory(
        db_session, confidence=0.9, successful_uses=1, failed_uses=4
    )
    proposal = await propose_memory_recalibration(
        db_session, migrated_settings, TelemetryRecorder(), record_id=record_id
    )
    await db_session.commit()
    assert proposal is not None

    await approve_proposal(db_session, TelemetryRecorder(), proposal.id)
    await db_session.commit()

    record = await db_session.get(MemoryRecord, record_id)
    assert record is not None
    assert record.confidence == pytest.approx(0.2)


async def test_approving_a_recalibration_proposal_is_a_no_op_if_confidence_already_drifted(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    record_id = await _seed_evidenced_memory(
        db_session, confidence=0.9, successful_uses=1, failed_uses=4
    )
    proposal = await propose_memory_recalibration(
        db_session, migrated_settings, TelemetryRecorder(), record_id=record_id
    )
    await db_session.commit()
    assert proposal is not None

    # Something else already changed the record's confidence since the
    # proposal was created -- re-check-before-mutate must refuse to
    # clobber it, the same staleness guard apply_gc_plan() uses.
    record = await db_session.get(MemoryRecord, record_id)
    assert record is not None
    record.confidence = 0.55
    await db_session.flush()

    await approve_proposal(db_session, TelemetryRecorder(), proposal.id)
    await db_session.commit()

    record = await db_session.get(MemoryRecord, record_id)
    assert record is not None
    assert record.confidence == 0.55
