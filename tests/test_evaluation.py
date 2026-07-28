"""Tests for acr.evaluation.evaluators / panel (master §1041-1059)."""

from __future__ import annotations

import pytest

from acr.evaluation.evaluators import ChecklistEvaluator, ExactMatchEvaluator, Predicate
from acr.evaluation.models import EvaluationCriterion
from acr.evaluation.panel import evaluate_with_panel


def test_exact_match_evaluator_passes_on_equal_output() -> None:
    evaluator = ExactMatchEvaluator()
    result = evaluator.evaluate("hello", "hello")
    assert result.passed is True
    assert result.overall_score == 1.0


def test_exact_match_evaluator_fails_on_unequal_output() -> None:
    evaluator = ExactMatchEvaluator()
    result = evaluator.evaluate("hello", "goodbye")
    assert result.passed is False
    assert result.overall_score == 0.0


def test_checklist_evaluator_requires_all_predicates() -> None:
    predicates = [
        Predicate("nonempty", EvaluationCriterion.COMPLETENESS, lambda o, e: bool(o)),
        Predicate("has_evidence", EvaluationCriterion.EVIDENCE, lambda o, e: "evidence" in o),
    ]
    evaluator = ChecklistEvaluator("checklist", predicates)

    passing = evaluator.evaluate("here is my evidence", None)
    failing = evaluator.evaluate("no citations here", None)

    assert passing.passed is True
    assert failing.passed is False
    assert failing.overall_score == 0.5  # one of two predicates passed


def test_panel_requires_majority_agreement() -> None:
    always_pass = ExactMatchEvaluator("a")
    always_fail = ChecklistEvaluator(
        "b", [Predicate("never", EvaluationCriterion.CORRECTNESS, lambda o, e: False)]
    )
    tie_breaker = ExactMatchEvaluator("c")

    panel = evaluate_with_panel([always_pass, always_fail, tie_breaker], "x", "x")

    assert panel.passed is True  # 2 of 3 passed
    assert panel.agreement == 2 / 3


def test_panel_requires_at_least_one_evaluator() -> None:
    with pytest.raises(ValueError, match="at least one evaluator"):
        evaluate_with_panel([], "x", "x")
