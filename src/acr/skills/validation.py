"""Skill validation pipeline (master §717-731).

candidate -> schema validation -> dependency check -> static security scan
-> permission analysis -> sandbox execution -> unit tests -> scenario tests
-> adversarial tests -> benchmark -> evaluator review -> promotion decision

ACR has no code-execution engine yet (a skill package is metadata plus
human-readable instructions, not executable code), so the sandbox
execution / unit / scenario / adversarial / benchmark stages are honestly
reported SKIPPED rather than faked as passing — master §731: "A candidate
must not be promoted merely because it completes one task," and it
certainly must not be promoted on the strength of a check that never ran.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from acr.evaluation.evaluators import ChecklistEvaluator, Predicate
from acr.evaluation.models import EvaluationCriterion
from acr.security.injection import scan_for_injection
from acr.security.permissions import Capability
from acr.skills.format import SkillFormatError, load_instructions, load_manifest
from acr.skills.models import SkillRecord
from acr.telemetry.recorder import TelemetryRecorder
from acr.tools.registry import ToolRegistry

_KNOWN_CAPABILITIES = {c.value for c in Capability}
_UNVALIDATABLE_STAGES = (
    "sandbox_execution",
    "unit_tests",
    "scenario_tests",
    "adversarial_tests",
    "benchmark",
)


class StageStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class StageResult:
    name: str
    status: StageStatus
    detail: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    skill_id: str
    stages: list[StageResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Promotion-eligible: no stage explicitly failed. Skipped stages
        don't count as evidence either way — see module docstring."""
        return all(stage.status is not StageStatus.FAILED for stage in self.stages)

    def stage(self, name: str) -> StageResult | None:
        return next((s for s in self.stages if s.name == name), None)


async def run_validation(
    session: AsyncSession,
    record: SkillRecord,
    *,
    tool_registry: ToolRegistry | None = None,
    telemetry: TelemetryRecorder | None = None,
) -> ValidationReport:
    stages: list[StageResult] = []
    skill_dir = Path(record.path)

    # 1. SCHEMA VALIDATION
    try:
        manifest = load_manifest(skill_dir)
    except SkillFormatError as exc:
        stages.append(StageResult("schema_validation", StageStatus.FAILED, str(exc)))
        report = ValidationReport(record.id, stages)
        await _emit(session, telemetry, report)
        return report
    stages.append(StageResult("schema_validation", StageStatus.PASSED, "SKILL.yaml is valid"))

    # 2. DEPENDENCY CHECK
    if tool_registry is None or not manifest.tools:
        stages.append(
            StageResult(
                "dependency_check", StageStatus.SKIPPED, "no tool registry or no declared tools"
            )
        )
    else:
        known_tools = {tool.name for tool in tool_registry.list_tools()}
        missing = [name for name in manifest.tools if name not in known_tools]
        if missing:
            stages.append(
                StageResult(
                    "dependency_check", StageStatus.FAILED, f"unknown tools: {', '.join(missing)}"
                )
            )
        else:
            stages.append(
                StageResult(
                    "dependency_check", StageStatus.PASSED, "all declared tools are registered"
                )
            )

    # 3. STATIC SECURITY SCAN — over every piece of human-authored text in
    # the package, not just the description (instructions.md is the part a
    # model would actually read and could carry injected directives).
    instructions = load_instructions(skill_dir) or ""
    scan = scan_for_injection(
        "\n".join([manifest.description, manifest.applicability, instructions])
    )
    if scan.suspicious:
        stages.append(
            StageResult(
                "security_scan", StageStatus.FAILED, f"matched: {', '.join(scan.matched_patterns)}"
            )
        )
    else:
        stages.append(
            StageResult("security_scan", StageStatus.PASSED, "no known injection patterns")
        )

    # 4. PERMISSION ANALYSIS — every declared permission must be a
    # recognized capability (master §1131-1146); an unrecognized string
    # would deny at authorization time anyway (Phase 7), so catch it here.
    unknown_permissions = [p for p in manifest.permissions if p not in _KNOWN_CAPABILITIES]
    if unknown_permissions:
        stages.append(
            StageResult(
                "permission_analysis",
                StageStatus.FAILED,
                f"unrecognized capabilities: {', '.join(unknown_permissions)}",
            )
        )
    else:
        stages.append(
            StageResult(
                "permission_analysis", StageStatus.PASSED, "all permissions are known capabilities"
            )
        )

    # 5-9. SANDBOX EXECUTION / UNIT / SCENARIO / ADVERSARIAL TESTS / BENCHMARK
    for name in _UNVALIDATABLE_STAGES:
        stages.append(StageResult(name, StageStatus.SKIPPED, "no code-execution engine exists yet"))

    # 10. EVALUATOR REVIEW — manifest completeness, via the Phase 5 framework.
    predicates = [
        Predicate(
            "has_description",
            EvaluationCriterion.COMPLETENESS,
            lambda _o, _e: bool(manifest.description.strip()),
        ),
        Predicate(
            "has_applicability",
            EvaluationCriterion.COMPLETENESS,
            lambda _o, _e: bool(manifest.applicability.strip()),
        ),
        Predicate(
            "has_verification",
            EvaluationCriterion.COMPLETENESS,
            lambda _o, _e: bool(manifest.verification.strip()),
        ),
    ]
    evaluation = ChecklistEvaluator("skill_manifest_completeness", predicates).evaluate(None, None)
    stages.append(
        StageResult(
            "evaluator_review",
            StageStatus.PASSED if evaluation.passed else StageStatus.FAILED,
            "; ".join(score.rationale for score in evaluation.scores),
        )
    )

    report = ValidationReport(record.id, stages)
    await _emit(session, telemetry, report)
    return report


async def _emit(
    session: AsyncSession, telemetry: TelemetryRecorder | None, report: ValidationReport
) -> None:
    if telemetry is None:
        return
    await telemetry.emit(
        session,
        "skill.validation",
        payload={
            "skill_id": report.skill_id,
            "passed": report.passed,
            "stages": [
                {"name": s.name, "status": s.status.value, "detail": s.detail}
                for s in report.stages
            ],
        },
    )
