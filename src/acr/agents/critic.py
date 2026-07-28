"""Agent output review (master §747-763's `verification_requirements`).

Reuses the Phase 5 evaluation panel rather than a bespoke agent-specific
review mechanism — an agent's completed `Task` is reviewed the same way any
other evaluated output is.
"""

from __future__ import annotations

from acr.core.tasks.models import Task, TaskStatus
from acr.evaluation.evaluators import ChecklistEvaluator, Predicate
from acr.evaluation.models import EvaluationCriterion
from acr.evaluation.panel import PanelResult, evaluate_with_panel


def review_agent_task(task: Task) -> PanelResult:
    """A minimal but real checklist: did the agent's task actually
    complete, and did it reach a terminal state (not left dangling)."""
    predicates = [
        Predicate(
            "completed",
            EvaluationCriterion.CORRECTNESS,
            lambda t, _e: t.status is TaskStatus.COMPLETED,
        ),
        Predicate(
            "is_terminal",
            EvaluationCriterion.CONSTRAINT_COMPLIANCE,
            lambda t, _e: t.is_terminal,
        ),
    ]
    evaluator = ChecklistEvaluator("agent_task_review", predicates)
    return evaluate_with_panel([evaluator], task, None)
