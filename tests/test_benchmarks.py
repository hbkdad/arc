"""Tests for acr.benchmarks (master §1061-1090)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.benchmarks import memory_recall
from acr.benchmarks.models import BenchmarkCase
from acr.benchmarks.runner import run_suite
from acr.evaluation.evaluators import ExactMatchEvaluator


async def test_memory_recall_suite_passes_against_real_retrieval(
    db_session: AsyncSession,
) -> None:
    await memory_recall.seed(db_session)
    cases = memory_recall.build_cases(db_session)

    run = await run_suite(db_session, memory_recall.SUITE_NAME, cases, ExactMatchEvaluator())
    await db_session.commit()

    assert run.total_cases == len(memory_recall._FIXTURES)
    assert run.passed_cases == run.total_cases
    assert run.score == 1.0


async def test_memory_recall_suite_fails_without_seeding(db_session: AsyncSession) -> None:
    # No seed() call: retrieve() has nothing to find.
    cases = memory_recall.build_cases(db_session)

    run = await run_suite(db_session, memory_recall.SUITE_NAME, cases, ExactMatchEvaluator())

    assert run.passed_cases == 0
    assert run.score == 0.0


async def test_run_suite_persists_case_details(db_session: AsyncSession) -> None:
    async def always_true() -> bool:
        return True

    case = BenchmarkCase(
        id="trivial", category="smoke", description="always true", run=always_true, expected=True
    )

    run = await run_suite(db_session, "smoke-suite", [case], ExactMatchEvaluator())

    assert run.details["cases"][0]["case_id"] == "trivial"
    assert run.details["cases"][0]["passed"] is True
