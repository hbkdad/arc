"""Memory write control (master §553-575).

Deterministic v1 policy: no permanent memory without evidence (master
principle #22), no silent duplicate/contradictory accumulation (§561-562).
This is intentionally rule-based rather than LLM-scored — Phase 8 (Learning)
can introduce a learned policy once there's evidence it outperforms these
rules; until then a learned policy would be exactly the kind of "permanent
learning without evidence" principle #22 forbids.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory.models import MemoryRecord, MemoryScope, MemoryStatus, MemoryType, utcnow

MIN_CONFIDENCE_TO_STORE = 0.2
MIN_CONFIDENCE_FOR_CONFIRMED = 0.75


class WriteDecision(StrEnum):
    IGNORE = "ignore"
    STORE_TEMPORARY = "store_temporary"
    STORE_CANDIDATE = "store_candidate"
    STORE_CONFIRMED = "store_confirmed"
    SUPERSEDE_EXISTING = "supersede_existing"
    REQUEST_VERIFICATION = "request_verification"
    QUARANTINE = "quarantine"


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    type: MemoryType
    scope: MemoryScope
    subject: str
    content: str
    source_type: str
    confidence: float = 0.5
    importance: float = 0.5
    evidence: str | None = None
    source_id: str | None = None
    structured_payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class WriteEvaluation:
    decision: WriteDecision
    reason: str
    existing: MemoryRecord | None = None


async def _find_existing(session: AsyncSession, candidate: MemoryCandidate) -> MemoryRecord | None:
    stmt = (
        select(MemoryRecord)
        .where(MemoryRecord.type == candidate.type)
        .where(MemoryRecord.scope == candidate.scope)
        .where(MemoryRecord.subject == candidate.subject)
        .where(MemoryRecord.status.in_((MemoryStatus.CANDIDATE, MemoryStatus.CONFIRMED)))
        .order_by(MemoryRecord.updated_at.desc())
    )
    return (await session.execute(stmt)).scalars().first()


async def evaluate(session: AsyncSession, candidate: MemoryCandidate) -> WriteEvaluation:
    if not candidate.content.strip():
        return WriteEvaluation(WriteDecision.IGNORE, "empty content")

    if candidate.confidence < MIN_CONFIDENCE_TO_STORE:
        return WriteEvaluation(WriteDecision.IGNORE, "confidence below storage threshold")

    existing = await _find_existing(session, candidate)

    if existing is not None and existing.content == candidate.content:
        return WriteEvaluation(WriteDecision.IGNORE, "duplicate of existing memory", existing)

    if existing is not None:
        if candidate.evidence is None:
            return WriteEvaluation(
                WriteDecision.REQUEST_VERIFICATION,
                "contradicts existing memory but candidate has no evidence",
                existing,
            )
        return WriteEvaluation(
            WriteDecision.SUPERSEDE_EXISTING,
            "evidence-backed new value for an existing subject",
            existing,
        )

    if candidate.evidence is None:
        return WriteEvaluation(WriteDecision.QUARANTINE, "new fact with no evidence")

    if candidate.type is MemoryType.TEMPORARY:
        return WriteEvaluation(WriteDecision.STORE_TEMPORARY, "explicitly temporary")

    if candidate.confidence >= MIN_CONFIDENCE_FOR_CONFIRMED:
        return WriteEvaluation(WriteDecision.STORE_CONFIRMED, "high confidence, evidence-backed")

    return WriteEvaluation(
        WriteDecision.STORE_CANDIDATE, "evidence-backed but below confirmation threshold"
    )


def _new_record(
    candidate: MemoryCandidate,
    *,
    status: MemoryStatus,
    supersedes: str | None = None,
    valid_from: datetime | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        type=candidate.type,
        scope=candidate.scope,
        subject=candidate.subject,
        content=candidate.content,
        structured_payload=candidate.structured_payload or {},
        confidence=candidate.confidence,
        importance=candidate.importance,
        source_type=candidate.source_type,
        source_id=candidate.source_id,
        evidence=candidate.evidence,
        status=status,
        supersedes=supersedes,
        valid_from=valid_from or utcnow(),
    )


async def apply(
    session: AsyncSession, candidate: MemoryCandidate, evaluation: WriteEvaluation
) -> MemoryRecord | None:
    """Apply a `WriteEvaluation`. Returns the resulting/affected record, if any."""
    decision = evaluation.decision

    if decision in (WriteDecision.IGNORE, WriteDecision.REQUEST_VERIFICATION):
        return evaluation.existing

    if decision is WriteDecision.QUARANTINE:
        record = _new_record(candidate, status=MemoryStatus.QUARANTINED)
        session.add(record)
        await session.flush()
        return record

    if decision is WriteDecision.SUPERSEDE_EXISTING and evaluation.existing is not None:
        old = evaluation.existing
        now = utcnow()
        old.status = MemoryStatus.SUPERSEDED
        old.valid_until = now
        new = _new_record(
            candidate, status=MemoryStatus.CONFIRMED, supersedes=old.id, valid_from=now
        )
        session.add(new)
        await session.flush()
        old.superseded_by = new.id
        await session.flush()
        return new

    status = {
        WriteDecision.STORE_TEMPORARY: MemoryStatus.CANDIDATE,
        WriteDecision.STORE_CANDIDATE: MemoryStatus.CANDIDATE,
        WriteDecision.STORE_CONFIRMED: MemoryStatus.CONFIRMED,
    }[decision]
    record = _new_record(candidate, status=status)
    session.add(record)
    await session.flush()
    return record


async def remember(
    session: AsyncSession, candidate: MemoryCandidate
) -> tuple[WriteEvaluation, MemoryRecord | None]:
    """Convenience: evaluate + apply in one call."""
    evaluation = await evaluate(session, candidate)
    record = await apply(session, candidate, evaluation)
    return evaluation, record
