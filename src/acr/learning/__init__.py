"""Learning: experience distillation, utility updates, candidate memory
promotion, candidate skill generation (master §631-644, §697-716)."""

from acr.learning.consolidation import GCAction, GCPlan, apply_gc_plan, plan_gc
from acr.learning.distillation import (
    DistillationResult,
    TaskNotFoundError,
    distill_and_remember,
    distill_task,
)
from acr.learning.failure_intelligence import SimilarFailure, find_similar_failures
from acr.learning.promotion import PromotionReport, promote_candidates
from acr.learning.routing_optimization import (
    ModelOutcome,
    RoutingComparison,
    compare_models,
    model_outcomes_for_task_class,
)
from acr.learning.self_practice import PracticeRun, run_self_practice
from acr.learning.skill_generation import (
    RepeatedPattern,
    detect_repeated_successes,
    generate_candidate_skill,
)
from acr.learning.utility import record_skill_outcome

__all__ = [
    "DistillationResult",
    "GCAction",
    "GCPlan",
    "ModelOutcome",
    "PracticeRun",
    "PromotionReport",
    "RepeatedPattern",
    "RoutingComparison",
    "SimilarFailure",
    "TaskNotFoundError",
    "apply_gc_plan",
    "compare_models",
    "detect_repeated_successes",
    "distill_and_remember",
    "distill_task",
    "find_similar_failures",
    "generate_candidate_skill",
    "model_outcomes_for_task_class",
    "plan_gc",
    "promote_candidates",
    "record_skill_outcome",
    "run_self_practice",
]
