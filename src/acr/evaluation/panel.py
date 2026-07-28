"""Multi-evaluator panels (master §1041-1059: "multiple independent
evaluators"; "Do not use one model's confidence as ground truth.").

A panel runs every evaluator independently over the same (output, expected)
pair and aggregates by majority vote — one evaluator's `passed` never
decides the outcome alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acr.evaluation.evaluators import Evaluator
from acr.evaluation.models import EvaluationResult


@dataclass(frozen=True, slots=True)
class PanelResult:
    results: list[EvaluationResult]
    passed: bool
    agreement: float  # fraction of evaluators that agreed with the majority verdict

    @property
    def mean_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.overall_score for r in self.results) / len(self.results)


def evaluate_with_panel(evaluators: list[Evaluator], output: Any, expected: Any) -> PanelResult:
    if not evaluators:
        raise ValueError("a panel needs at least one evaluator")

    results = [e.evaluate(output, expected) for e in evaluators]
    pass_votes = sum(1 for r in results if r.passed)
    majority_passed = pass_votes * 2 > len(results)
    agreeing = pass_votes if majority_passed else len(results) - pass_votes
    agreement = agreeing / len(results)

    return PanelResult(results=results, passed=majority_passed, agreement=agreement)
