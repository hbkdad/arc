"""Tests for acr.evaluation.waste_analyzer (master §1026-1039)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.context.attribution import record_attribution
from acr.context.compiler import compile_context
from acr.evaluation.waste_analyzer import analyze_context_utilization, find_duplicate_memories
from acr.memory import MemoryCandidate, MemoryScope, MemoryType
from acr.memory.write_controller import remember
from acr.telemetry.recorder import TelemetryRecorder


async def _seed(session: AsyncSession, subject: str, content: str) -> None:
    await remember(
        session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject=subject,
            content=content,
            source_type="session",
            confidence=0.9,
            evidence="test fixture",
        ),
    )


async def test_find_duplicate_memories_detects_shared_content_across_subjects(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, "acr.a", "ACR uses SQLite.")
    await _seed(db_session, "acr.b", "ACR uses SQLite.")
    await _seed(db_session, "acr.c", "ACR uses Typer for its CLI.")

    groups = await find_duplicate_memories(db_session)

    assert len(groups) == 1
    assert groups[0].content == "ACR uses SQLite."
    assert len(groups[0].record_ids) == 2


async def test_find_duplicate_memories_reports_nothing_when_all_unique(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, "acr.a", "ACR uses SQLite.")
    await _seed(db_session, "acr.b", "ACR uses Typer for its CLI.")

    assert await find_duplicate_memories(db_session) == []


async def test_analyze_context_utilization_with_no_history_is_fully_utilized(
    db_session: AsyncSession,
) -> None:
    report = await analyze_context_utilization(db_session)

    assert report.sample_count == 0
    assert report.utilization == 1.0
    assert report.wasted_tokens == 0


async def test_analyze_context_utilization_reflects_attribution_history(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, "acr.a", "ACR uses SQLite for local storage.")
    await _seed(db_session, "acr.b", "ACR uses SQLite for the memory registry too.")

    bundle = await compile_context(db_session, task_objective="SQLite", token_budget=4000)
    assert len(bundle.items) == 2

    used = {bundle.items[0].id}
    await record_attribution(
        db_session,
        bundle,
        used_item_ids=used,
        success=True,
        telemetry=TelemetryRecorder(),
        task_id="task-1",
    )
    await db_session.commit()

    report = await analyze_context_utilization(db_session)

    assert report.sample_count == 1
    assert report.total_bundle_tokens == bundle.total_tokens
    assert report.total_referenced_tokens == bundle.items[0].token_cost
    assert 0.0 < report.utilization < 1.0
    assert report.wasted_tokens == bundle.items[1].token_cost
