"""Tests for acr.memory.write_controller (master §553-575)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory import MemoryCandidate, MemoryScope, MemoryStatus, MemoryType, WriteDecision
from acr.memory.write_controller import evaluate, remember


def _candidate(**overrides: object) -> MemoryCandidate:
    defaults: dict[str, object] = dict(
        type=MemoryType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        subject="acr.backend.database",
        content="ACR uses SQLite for local storage.",
        source_type="session",
        confidence=0.8,
        evidence="observed in pyproject.toml dependencies",
    )
    defaults.update(overrides)
    return MemoryCandidate(**defaults)  # type: ignore[arg-type]


async def test_empty_content_is_ignored(db_session: AsyncSession) -> None:
    evaluation = await evaluate(db_session, _candidate(content="   "))
    assert evaluation.decision is WriteDecision.IGNORE


async def test_low_confidence_is_ignored(db_session: AsyncSession) -> None:
    evaluation = await evaluate(db_session, _candidate(confidence=0.05))
    assert evaluation.decision is WriteDecision.IGNORE


async def test_new_fact_without_evidence_is_quarantined(db_session: AsyncSession) -> None:
    evaluation = await evaluate(db_session, _candidate(evidence=None))
    assert evaluation.decision is WriteDecision.QUARANTINE


async def test_a_quarantined_fact_is_actually_persisted_with_quarantined_status(
    db_session: AsyncSession,
) -> None:
    # evaluate() alone only asserts the *decision* -- this exercises the
    # real remember()/apply() persistence path a bug in the QUARANTINE
    # branch (wrong status, missing session.add) would otherwise slip
    # through silently.
    evaluation, record = await remember(db_session, _candidate(evidence=None))
    assert evaluation.decision is WriteDecision.QUARANTINE
    assert record is not None
    assert record.status is MemoryStatus.QUARANTINED
    assert record.id is not None


async def test_high_confidence_evidence_backed_fact_is_confirmed(db_session: AsyncSession) -> None:
    evaluation, record = await remember(db_session, _candidate(confidence=0.9))
    assert evaluation.decision is WriteDecision.STORE_CONFIRMED
    assert record is not None
    assert record.status is MemoryStatus.CONFIRMED


async def test_medium_confidence_fact_is_stored_as_candidate(db_session: AsyncSession) -> None:
    evaluation, record = await remember(db_session, _candidate(confidence=0.5))
    assert evaluation.decision is WriteDecision.STORE_CANDIDATE
    assert record is not None
    assert record.status is MemoryStatus.CANDIDATE


async def test_identical_content_is_deduplicated(db_session: AsyncSession) -> None:
    await remember(db_session, _candidate(confidence=0.9))
    evaluation, record = await remember(db_session, _candidate(confidence=0.9))
    assert evaluation.decision is WriteDecision.IGNORE
    assert record is not None  # the pre-existing record, unchanged


async def test_contradicting_fact_without_evidence_requests_verification(
    db_session: AsyncSession,
) -> None:
    await remember(db_session, _candidate(confidence=0.9))
    evaluation, _ = await remember(
        db_session, _candidate(confidence=0.9, content="ACR uses PostgreSQL.", evidence=None)
    )
    assert evaluation.decision is WriteDecision.REQUEST_VERIFICATION


async def test_contradicting_fact_with_evidence_supersedes(db_session: AsyncSession) -> None:
    _, original = await remember(db_session, _candidate(confidence=0.9))
    assert original is not None

    evaluation, replacement = await remember(
        db_session, _candidate(confidence=0.9, content="ACR uses PostgreSQL.")
    )

    assert evaluation.decision is WriteDecision.SUPERSEDE_EXISTING
    assert replacement is not None
    assert replacement.supersedes == original.id
    await db_session.refresh(original)
    assert original.status is MemoryStatus.SUPERSEDED
    assert original.superseded_by == replacement.id


async def test_low_confidence_correction_supersedes_as_candidate_not_confirmed(
    db_session: AsyncSession,
) -> None:
    # A correction must clear the same MIN_CONFIDENCE_FOR_CONFIRMED bar a
    # brand-new fact does (see test_medium_confidence_fact_is_stored_as_candidate)
    # -- otherwise a weakly-evidenced "correction" could jump straight to
    # CONFIRMED (the only status current()/memory_trust_level() treat as
    # trusted/temporally-current) without ever earning that trust level.
    _, original = await remember(db_session, _candidate(confidence=0.9))
    assert original is not None

    evaluation, replacement = await remember(
        db_session, _candidate(confidence=0.3, content="ACR uses PostgreSQL.")
    )

    assert evaluation.decision is WriteDecision.SUPERSEDE_EXISTING
    assert replacement is not None
    assert replacement.status is MemoryStatus.CANDIDATE


async def test_temporary_type_is_stored_temporarily(db_session: AsyncSession) -> None:
    evaluation, record = await remember(db_session, _candidate(type=MemoryType.TEMPORARY))
    assert evaluation.decision is WriteDecision.STORE_TEMPORARY
    assert record is not None
