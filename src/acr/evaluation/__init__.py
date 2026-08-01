"""Evaluation system: evaluators, panels, regression detection, waste
analysis (master §1041-1090, §1026-1039)."""

from acr.evaluation.calibration import (
    CalibrationBin,
    CalibrationReport,
    MiscalibratedRecord,
    compute_calibration,
    find_miscalibrated_records,
)
from acr.evaluation.evaluators import (
    ChecklistEvaluator,
    Evaluator,
    ExactMatchEvaluator,
    Predicate,
)
from acr.evaluation.models import CriterionScore, EvaluationCriterion, EvaluationResult
from acr.evaluation.panel import PanelResult, evaluate_with_panel
from acr.evaluation.regression import RegressionReport, detect_regression
from acr.evaluation.waste_analyzer import (
    DuplicateGroup,
    UtilizationReport,
    analyze_context_utilization,
    find_duplicate_memories,
)

__all__ = [
    "CalibrationBin",
    "CalibrationReport",
    "ChecklistEvaluator",
    "CriterionScore",
    "DuplicateGroup",
    "EvaluationCriterion",
    "EvaluationResult",
    "Evaluator",
    "ExactMatchEvaluator",
    "MiscalibratedRecord",
    "PanelResult",
    "Predicate",
    "RegressionReport",
    "UtilizationReport",
    "analyze_context_utilization",
    "compute_calibration",
    "detect_regression",
    "evaluate_with_panel",
    "find_duplicate_memories",
    "find_miscalibrated_records",
]
