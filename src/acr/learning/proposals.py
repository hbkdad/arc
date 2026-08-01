"""Controlled self-improvement (master §1721-1727, §99).

"Controlled" is the operative word: every self-improvement action is a
`Proposal` — evidence plus a recommendation — not a change applied
directly. A proposal only ever comes from an existing, evidence-producing
comparison (right now: Phase 9's `compare_versions()`); nothing here
invents its own quality signal. Proposals require explicit human approval
before taking effect by default (`Settings.auto_apply_proposals=False`);
flipping that setting is the one, single escape hatch to autonomous
application — an explicit user decision, not a default.

Scope boundary (also explicit user intent: self-improve "for the design
and intent it was given," not unboundedly): a proposal can only ever
invoke a mechanism this codebase already exposes as a reviewable, gated
operation (`acr.skills.evolution.promote_evolution`, itself safe-mode-
aware; `MemoryRecord.confidence`, a runtime value ACR already mutates
automatically via `acr.context.attribution` with no human gate at all,
see `MEMORY_RECALIBRATION` below) — or, when no safe mechanism to
auto-apply exists at all (`ROUTING_OPTIMIZATION`: see
`acr.learning.routing_optimization`), stay strictly advisory, never
silently mutating environment/config as a side effect of approval. There
is no proposal kind — and never will be one added here — that edits
ACR's own source code, dependencies, or permission grants; those stay
entirely outside what "self-improvement" means in this system.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, select
from sqlalchemy import Enum as SAEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from acr.config import Settings
from acr.db.base import Base
from acr.evaluation.calibration import DEFAULT_MIN_CALIBRATION_GAP
from acr.learning.routing_optimization import ModelOutcome, RoutingComparison, compare_models
from acr.memory.models import MemoryRecord
from acr.security.audit import record_audit_event
from acr.security.safe_mode import require_not_safe_mode
from acr.skills.evolution import EvolutionComparison, compare_versions, promote_evolution
from acr.skills.registry import SkillNotFoundError, get
from acr.skills.trajectory_audit import TrajectoryAuditResult, TrajectoryVerdict
from acr.telemetry.recorder import TelemetryRecorder


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProposalKind(StrEnum):
    SKILL_EVOLUTION_PROMOTION = "skill_evolution_promotion"
    ROUTING_OPTIMIZATION = "routing_optimization"
    MEMORY_RECALIBRATION = "memory_recalibration"


class MemoryRecordNotFoundError(LookupError):
    """Raised by `propose_memory_recalibration()` for an unknown record id."""


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPLIED = "auto_applied"


class SelfImprovementDisabledError(RuntimeError):
    """Raised when a proposal is attempted with `Settings.self_improvement_enabled=False`."""


class ProposalNotFoundError(LookupError):
    """Raised when approving/rejecting an unknown proposal id."""


class ProposalNotPendingError(ValueError):
    """Raised when approving/rejecting a proposal that's already been decided."""


class Proposal(Base):
    """One self-improvement proposal: evidence + a recommendation, never an
    applied change by itself (master §1721-1727 — "controlled")."""

    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)
    kind: Mapped[ProposalKind] = mapped_column(SAEnum(ProposalKind))
    subject: Mapped[str] = mapped_column(index=True)  # e.g. a skill id
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reason: Mapped[str]
    status: Mapped[ProposalStatus] = mapped_column(
        SAEnum(ProposalStatus), default=ProposalStatus.PENDING, index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(default=None)


async def propose_skill_evolution(
    session: AsyncSession,
    settings: Settings,
    telemetry: TelemetryRecorder,
    *,
    baseline_id: str,
    candidate_id: str,
    trajectory_audit: TrajectoryAuditResult | None = None,
) -> Proposal | None:
    """Compare `candidate_id` against `baseline_id` (Phase 9) and, only if the
    comparison actually recommends promotion, create a `Proposal` for it.

    Never proposes a regression — `compare_versions()`'s own recommendation
    is the sole gate by default. Returns `None` (not a rejected `Proposal`)
    when the candidate doesn't recommend promotion: a non-improvement isn't
    a proposal that got turned down, it's simply not evidence of anything to
    propose (master principle: never publish a result the evidence doesn't
    support).

    `trajectory_audit`, if given (from `acr.skills.trajectory_audit
    .audit_trajectories()`), is an *additional* evidence gate, not a
    replacement — `compare_versions()`'s numeric recommendation AND the
    audit's real judged verdict must both favor the candidate before a
    proposal is created, the same two-independent-signals caution used
    elsewhere in this session. Left `None` (the default), behavior is
    exactly `compare_versions()`-only, unchanged from before this
    parameter existed — running an audit costs real provider tokens
    (two trajectory runs plus a judge call), so this function stays free
    unless a caller explicitly opts in.
    """
    if not settings.self_improvement_enabled:
        raise SelfImprovementDisabledError(
            "self-improvement is disabled (ACR_SELF_IMPROVEMENT_ENABLED=0)"
        )

    baseline = await get(session, baseline_id)
    if baseline is None:
        raise SkillNotFoundError(baseline_id)
    candidate = await get(session, candidate_id)
    if candidate is None:
        raise SkillNotFoundError(candidate_id)

    comparison = compare_versions(baseline, candidate)
    if not comparison.recommend_promote:
        return None
    if trajectory_audit is not None and trajectory_audit.verdict is not TrajectoryVerdict.CANDIDATE:
        return None

    payload: dict[str, Any] = asdict(comparison)
    reason = comparison.reason
    if trajectory_audit is not None:
        payload["trajectory_audit"] = asdict(trajectory_audit)
        reason = (
            f"{reason}; trajectory audit also favors the candidate: {trajectory_audit.rationale}"
        )

    auto_apply = settings.auto_apply_proposals
    proposal = Proposal(
        kind=ProposalKind.SKILL_EVOLUTION_PROMOTION,
        subject=baseline_id,
        payload=payload,
        reason=reason,
        status=ProposalStatus.PENDING,
    )
    session.add(proposal)
    await session.flush()

    await record_audit_event(
        session,
        telemetry,
        action=f"proposal.create:{proposal.id}",
        outcome="pending",
        detail={"kind": proposal.kind.value, "subject": proposal.subject},
    )

    if auto_apply:
        await _apply(session, proposal, safe_mode=settings.safe_mode)
        proposal.status = ProposalStatus.AUTO_APPLIED
        proposal.decided_at = _utcnow()
        await record_audit_event(
            session,
            telemetry,
            action=f"proposal.auto_apply:{proposal.id}",
            outcome="applied",
            detail={"kind": proposal.kind.value, "subject": proposal.subject},
        )

    return proposal


async def propose_routing_optimization(
    session: AsyncSession,
    settings: Settings,
    telemetry: TelemetryRecorder,
    *,
    task_class: str,
    current: ModelOutcome,
    candidate: ModelOutcome,
) -> Proposal | None:
    """Compare `candidate` against `current` (both `ModelOutcome`s from
    `routing_optimization.model_outcomes_for_task_class()`) and, only if
    the comparison actually recommends switching, create an advisory
    `Proposal` for it.

    Never auto-applies regardless of `Settings.auto_apply_proposals` --
    unlike skill evolution, there is no safe mechanism to change routing
    on ACR's own authority (see module docstring and
    `acr.learning.routing_optimization`'s). Approving this proposal kind
    means "a human reviewed the evidence," not "a change was applied."
    """
    if not settings.self_improvement_enabled:
        raise SelfImprovementDisabledError(
            "self-improvement is disabled (ACR_SELF_IMPROVEMENT_ENABLED=0)"
        )

    comparison: RoutingComparison = compare_models(current, candidate, task_class=task_class)
    if not comparison.recommend_switch:
        return None

    proposal = Proposal(
        kind=ProposalKind.ROUTING_OPTIMIZATION,
        subject=task_class,
        payload=asdict(comparison),
        reason=comparison.reason,
        status=ProposalStatus.PENDING,
    )
    session.add(proposal)
    await session.flush()

    await record_audit_event(
        session,
        telemetry,
        action=f"proposal.create:{proposal.id}",
        outcome="pending",
        detail={"kind": proposal.kind.value, "subject": proposal.subject},
    )

    return proposal


@dataclass(frozen=True, slots=True)
class RecalibrationComparison:
    record_id: str
    subject: str
    old_confidence: float
    new_confidence: float
    uses: int
    reason: str


async def propose_memory_recalibration(
    session: AsyncSession,
    settings: Settings,
    telemetry: TelemetryRecorder,
    *,
    record_id: str,
    min_uses: int = 1,
    min_gap: float = DEFAULT_MIN_CALIBRATION_GAP,
) -> Proposal | None:
    """Compare `record_id`'s stored `confidence` against its own real
    `successful_uses`/`failed_uses` outcome (`acr.evaluation.calibration`)
    and, only if the gap is significant, propose resetting `confidence` to
    the real empirical rate.

    Closes a loop `acr memory calibration` left purely diagnostic: that
    command can tell you a record's confidence looks miscalibrated, but
    nothing acted on it. Every other proposal kind here already mutates
    real ACR-owned runtime state on approval (skill status;
    `context.attribution` already mutates memory confidence-adjacent
    fields automatically, with no human gate at all) -- this is the same
    category of change, just made explicit, evidence-gated, and reviewable
    rather than silent. Returns `None` (not a rejected proposal) when the
    record doesn't have enough evidence or isn't significantly
    miscalibrated: absence of evidence isn't itself evidence to propose
    anything (master principle #22).
    """
    if not settings.self_improvement_enabled:
        raise SelfImprovementDisabledError(
            "self-improvement is disabled (ACR_SELF_IMPROVEMENT_ENABLED=0)"
        )

    record = await session.get(MemoryRecord, record_id)
    if record is None:
        raise MemoryRecordNotFoundError(record_id)

    uses = record.successful_uses + record.failed_uses
    if uses < min_uses:
        return None
    empirical = record.successful_uses / uses
    gap = record.confidence - empirical
    if abs(gap) < min_gap:
        return None

    comparison = RecalibrationComparison(
        record_id=record.id,
        subject=record.subject,
        old_confidence=record.confidence,
        new_confidence=empirical,
        uses=uses,
        reason=(
            f"stored confidence {record.confidence:.2f} vs real empirical "
            f"success rate {empirical:.2f} over {uses} recorded use(s) "
            f"(gap {gap:+.2f})"
        ),
    )

    auto_apply = settings.auto_apply_proposals
    proposal = Proposal(
        kind=ProposalKind.MEMORY_RECALIBRATION,
        subject=record.subject,
        payload=asdict(comparison),
        reason=comparison.reason,
        status=ProposalStatus.PENDING,
    )
    session.add(proposal)
    await session.flush()

    await record_audit_event(
        session,
        telemetry,
        action=f"proposal.create:{proposal.id}",
        outcome="pending",
        detail={"kind": proposal.kind.value, "subject": proposal.subject},
    )

    if auto_apply:
        await _apply(session, proposal, safe_mode=settings.safe_mode)
        proposal.status = ProposalStatus.AUTO_APPLIED
        proposal.decided_at = _utcnow()
        await record_audit_event(
            session,
            telemetry,
            action=f"proposal.auto_apply:{proposal.id}",
            outcome="applied",
            detail={"kind": proposal.kind.value, "subject": proposal.subject},
        )

    return proposal


async def _apply(session: AsyncSession, proposal: Proposal, *, safe_mode: bool) -> None:
    if proposal.kind is ProposalKind.SKILL_EVOLUTION_PROMOTION:
        # payload may carry an extra "trajectory_audit" key (see
        # propose_skill_evolution()) for transparency/review -- kept
        # alongside the comparison fields rather than nested away, so it
        # must be filtered back out here before reconstructing the
        # dataclass, or any trajectory-audited proposal would crash on
        # approval with an unexpected-keyword TypeError.
        comparison_fields = {f.name for f in fields(EvolutionComparison)}
        comparison = EvolutionComparison(
            **{k: v for k, v in proposal.payload.items() if k in comparison_fields}
        )
        baseline = await get(session, comparison.baseline_id)
        assert baseline is not None  # existed when the proposal was created
        await promote_evolution(session, baseline, comparison.candidate_id, safe_mode=safe_mode)
        return
    if proposal.kind is ProposalKind.ROUTING_OPTIMIZATION:
        # Advisory only -- see module docstring. Approving means "reviewed
        # by a human," not "changed": there is no safe, gated mechanism to
        # flip Settings.default_min_quality_tier from inside this process.
        return
    if proposal.kind is ProposalKind.MEMORY_RECALIBRATION:
        require_not_safe_mode(safe_mode, f"memory.recalibrate:{proposal.subject}")
        comparison = RecalibrationComparison(**proposal.payload)
        record = await session.get(MemoryRecord, comparison.record_id)
        if record is None:
            return  # deleted/archived since the proposal was created -- nothing to apply
        if record.confidence != comparison.old_confidence:
            # Drifted (or was already corrected) since this proposal was
            # evaluated -- re-check-before-mutate, same as
            # acr.learning.consolidation.apply_gc_plan()'s own pattern for
            # exactly this staleness risk.
            return
        record.confidence = comparison.new_confidence
        return
    raise NotImplementedError(f"no applier registered for proposal kind {proposal.kind!r}")


async def approve_proposal(
    session: AsyncSession,
    telemetry: TelemetryRecorder,
    proposal_id: str,
    *,
    safe_mode: bool = False,
) -> Proposal:
    proposal = await session.get(Proposal, proposal_id)
    if proposal is None:
        raise ProposalNotFoundError(proposal_id)
    if proposal.status is not ProposalStatus.PENDING:
        raise ProposalNotPendingError(f"proposal {proposal_id} is already {proposal.status.value}")

    await _apply(session, proposal, safe_mode=safe_mode)

    proposal.status = ProposalStatus.APPROVED
    proposal.decided_at = _utcnow()
    await record_audit_event(
        session,
        telemetry,
        action=f"proposal.approve:{proposal.id}",
        outcome="applied",
        detail={"kind": proposal.kind.value, "subject": proposal.subject},
    )
    return proposal


async def reject_proposal(
    session: AsyncSession, telemetry: TelemetryRecorder, proposal_id: str
) -> Proposal:
    proposal = await session.get(Proposal, proposal_id)
    if proposal is None:
        raise ProposalNotFoundError(proposal_id)
    if proposal.status is not ProposalStatus.PENDING:
        raise ProposalNotPendingError(f"proposal {proposal_id} is already {proposal.status.value}")

    proposal.status = ProposalStatus.REJECTED
    proposal.decided_at = _utcnow()
    await record_audit_event(
        session,
        telemetry,
        action=f"proposal.reject:{proposal.id}",
        outcome="rejected",
        detail={"kind": proposal.kind.value, "subject": proposal.subject},
    )
    return proposal


async def list_proposals(
    session: AsyncSession, *, status: ProposalStatus | None = None
) -> list[Proposal]:
    stmt = select(Proposal).order_by(Proposal.created_at.desc())
    if status is not None:
        stmt = stmt.where(Proposal.status == status)
    return list((await session.execute(stmt)).scalars().all())
