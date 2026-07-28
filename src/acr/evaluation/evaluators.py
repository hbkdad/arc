"""Deterministic evaluators (master §1041-1050).

`Evaluator` is the interface every evaluator implements — deterministic ones
here, an LLM-judge evaluator later once there's a real model call to grade
(master lists "LLM judges" as one evaluator *kind* among several, not a
requirement that every evaluation involve a model).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from acr.evaluation.models import CriterionScore, EvaluationCriterion, EvaluationResult


class Evaluator(ABC):
    name: str

    @abstractmethod
    def evaluate(self, output: Any, expected: Any) -> EvaluationResult: ...


@dataclass(frozen=True, slots=True)
class Predicate:
    name: str
    criterion: EvaluationCriterion
    check: Callable[[Any, Any], bool]


class ChecklistEvaluator(Evaluator):
    """Passes only if every named predicate holds. Fully deterministic —
    no paid model access required (master §1515)."""

    def __init__(self, name: str, predicates: list[Predicate]) -> None:
        self.name = name
        self._predicates = predicates

    def evaluate(self, output: Any, expected: Any) -> EvaluationResult:
        scores = []
        for predicate in self._predicates:
            ok = predicate.check(output, expected)
            scores.append(
                CriterionScore(
                    criterion=predicate.criterion,
                    score=1.0 if ok else 0.0,
                    rationale=f"{predicate.name}: {'passed' if ok else 'failed'}",
                )
            )
        return EvaluationResult(
            evaluator_name=self.name,
            passed=all(s.score == 1.0 for s in scores),
            scores=scores,
        )


class ExactMatchEvaluator(Evaluator):
    """Correctness-only evaluator: does `output == expected`?"""

    def __init__(self, name: str = "exact_match") -> None:
        self.name = name

    def evaluate(self, output: Any, expected: Any) -> EvaluationResult:
        matched = output == expected
        return EvaluationResult(
            evaluator_name=self.name,
            passed=matched,
            scores=[
                CriterionScore(
                    criterion=EvaluationCriterion.CORRECTNESS,
                    score=1.0 if matched else 0.0,
                    rationale=f"output {'==' if matched else '!='} expected",
                )
            ],
        )
