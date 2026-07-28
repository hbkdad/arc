"""Learning: experience distillation, utility updates, candidate memory
promotion, candidate skill generation (master §631-644, §697-716)."""

from acr.learning.distillation import (
    DistillationResult,
    TaskNotFoundError,
    distill_and_remember,
    distill_task,
)
from acr.learning.promotion import PromotionReport, promote_candidates
from acr.learning.skill_generation import (
    RepeatedPattern,
    detect_repeated_successes,
    generate_candidate_skill,
)
from acr.learning.utility import record_skill_outcome

__all__ = [
    "DistillationResult",
    "PromotionReport",
    "RepeatedPattern",
    "TaskNotFoundError",
    "detect_repeated_successes",
    "distill_and_remember",
    "distill_task",
    "generate_candidate_skill",
    "promote_candidates",
    "record_skill_outcome",
]
