"""Tests for acr.learning.failure_intelligence (master §615-629)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.learning.failure_intelligence import find_similar_failures
from acr.memory import FailurePayload, MemoryCandidate, MemoryScope, MemoryType
from acr.memory.write_controller import remember, remember_failure


async def test_finds_a_similar_recorded_failure(db_session: AsyncSession) -> None:
    await remember_failure(
        db_session,
        FailurePayload(
            task_class="ui-audit",
            symptom="dead status-fail CSS class made a disconnect state invisible",
            root_cause="JS-set className with no matching CSS rule",
            resolution="added the missing rule",
        ),
        subject="acr.dashboard.status_indicator",
        source_type="session",
        evidence="observed directly",
    )

    results = await find_similar_failures(
        db_session, objective="dead CSS class disconnect state", task_class="ui-audit"
    )

    assert len(results) == 1
    assert results[0].root_cause == "JS-set className with no matching CSS rule"
    assert results[0].resolution == "added the missing rule"


async def test_task_class_filter_excludes_a_failure_from_a_different_class(
    db_session: AsyncSession,
) -> None:
    await remember_failure(
        db_session,
        FailurePayload(task_class="code-review", symptom="missed a SQL injection"),
        subject="acr.review.security",
        source_type="session",
        evidence="observed directly",
    )

    results = await find_similar_failures(
        db_session, objective="missed a SQL injection", task_class="ui-audit"
    )

    assert results == []


async def test_a_free_form_failure_memory_without_the_schema_is_excluded_not_erroring(
    db_session: AsyncSession,
) -> None:
    # A FAILURE-typed memory predating this schema (or written by something
    # that never adopted it) has no task_class/symptom in structured_payload
    # -- must be silently skipped, never surfaced with fabricated fields.
    await remember(
        db_session,
        MemoryCandidate(
            type=MemoryType.FAILURE,
            scope=MemoryScope.PROJECT,
            subject="acr.legacy.failure",
            content="something went wrong once, no structure",
            source_type="session",
            confidence=0.8,
            evidence="observed directly",
        ),
    )

    results = await find_similar_failures(db_session, objective="something went wrong")

    assert results == []


async def test_returns_empty_list_when_no_failures_are_recorded(db_session: AsyncSession) -> None:
    results = await find_similar_failures(db_session, objective="anything at all")

    assert results == []
