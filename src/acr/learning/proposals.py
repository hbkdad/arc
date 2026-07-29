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
aware) — or, when no safe mechanism to auto-apply exists at all
(`ROUTING_OPTIMIZATION`: see `acr.learning.routing_optimization`), stay
strictly advisory, never silently mutating environment/config as a side
effect of approval. There is no proposal kind — and never will be one
added here — that edits ACR's own source code, dependencies, or
permission grants; those stay entirely outside what "self-improvement"
means in this system.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, select
from sqlalchemy import Enum as SAEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from acr.config import Settings
from acr.db.base import Base
from acr.learning.routing_optimization import ModelOutcome, RoutingComparison, compare_models
from acr.security.audit import record_audit_event
from acr.skills.evolution import EvolutionComparison, compare_versions, promote_evolution
from acr.skills.registry import SkillNotFoundError, get
from acr.telemetry.recorder import TelemetryRecorder


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProposalKind(StrEnum):
    SKILL_EVOLUTION_PROMOTION = "skill_evolution_promotion"
    ROUTING_OPTIMIZATION = "routing_optimization"


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
) -> Proposal | None:
    """Compare `candidate_id` against `baseline_id` (Phase 9) and, only if the
    comparison actually recommends promotion, create a `Proposal` for it.

    Never proposes a regression — `compare_versions()`'s own recommendation
    is the sole gate. Returns `None` (not a rejected `Proposal`) when the
    candidate doesn't recommend promotion: a non-improvement isn't a
    proposal that got turned down, it's simply not evidence of anything to
    propose (master principle: never publish a result the evidence doesn't
    support).
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

    auto_apply = settings.auto_apply_proposals
    proposal = Proposal(
        kind=ProposalKind.SKILL_EVOLUTION_PROMOTION,
        subject=baseline_id,
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


async def _apply(session: AsyncSession, proposal: Proposal, *, safe_mode: bool) -> None:
    if proposal.kind is ProposalKind.SKILL_EVOLUTION_PROMOTION:
        comparison = EvolutionComparison(**proposal.payload)
        baseline = await get(session, comparison.baseline_id)
        assert baseline is not None  # existed when the proposal was created
        await promote_evolution(session, baseline, comparison.candidate_id, safe_mode=safe_mode)
        return
    if proposal.kind is ProposalKind.ROUTING_OPTIMIZATION:
        # Advisory only -- see module docstring. Approving means "reviewed
        # by a human," not "changed": there is no safe, gated mechanism to
        # flip Settings.default_min_quality_tier from inside this process.
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
