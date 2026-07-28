"""Evaluation result types (master §1041-1059).

Evaluators score along the criteria master §1051-1058 lists. Not every
evaluator scores every criterion — an evaluator reports only the criteria it
actually judges, so `EvaluationResult.scores` is a sparse list, not a
fixed-width vector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class EvaluationCriterion(StrEnum):
    CORRECTNESS = "correctness"
    COMPLETENESS = "completeness"
    EVIDENCE = "evidence"
    CONSTRAINT_COMPLIANCE = "constraint_compliance"
    SECURITY = "security"
    EFFICIENCY = "efficiency"
    MAINTAINABILITY = "maintainability"


@dataclass(frozen=True, slots=True)
class CriterionScore:
    criterion: EvaluationCriterion
    score: float  # 0.0-1.0
    rationale: str


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    evaluator_name: str
    passed: bool
    scores: list[CriterionScore] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        if not self.scores:
            return 1.0 if self.passed else 0.0
        return sum(s.score for s in self.scores) / len(self.scores)
