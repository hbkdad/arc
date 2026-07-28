"""Benchmark runner (master §1061-1090).

Executes each case's `run()` for real against the actual ACR subsystem being
benchmarked, evaluates the output, and persists one aggregate `BenchmarkRun`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.benchmarks.models import BenchmarkCase, BenchmarkRun, CaseResult
from acr.evaluation.evaluators import Evaluator


async def run_suite(
    session: AsyncSession,
    suite_name: str,
    cases: list[BenchmarkCase],
    evaluator: Evaluator,
) -> BenchmarkRun:
    results: list[CaseResult] = []
    for case in cases:
        output = await case.run()
        evaluation = evaluator.evaluate(output, case.expected)
        rationale = "; ".join(s.rationale for s in evaluation.scores) or (
            "passed" if evaluation.passed else "failed"
        )
        results.append(
            CaseResult(
                case_id=case.id,
                passed=evaluation.passed,
                score=evaluation.overall_score,
                rationale=rationale,
            )
        )

    total = len(results)
    passed_cases = sum(1 for r in results if r.passed)
    score = sum(r.score for r in results) / total if total else 0.0

    run = BenchmarkRun(
        suite_name=suite_name,
        total_cases=total,
        passed_cases=passed_cases,
        score=score,
        details={
            "cases": [
                {
                    "case_id": r.case_id,
                    "passed": r.passed,
                    "score": r.score,
                    "rationale": r.rationale,
                }
                for r in results
            ]
        },
    )
    session.add(run)
    await session.flush()
    return run
