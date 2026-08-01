"""Tests for acr.skills.trajectory_audit."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.tasks.models import Step, StepKind, TaskRun, TaskStatus
from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider
from acr.providers.mock import MockProvider
from acr.skills.evolution import create_candidate_version
from acr.skills.registry import register
from acr.skills.trajectory_audit import (
    TrajectoryVerdict,
    _parse_verdict,
    audit_trajectories,
    run_skill_trajectory,
)
from acr.telemetry.recorder import TelemetryRecorder

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


class _VerdictProvider(ModelProvider):
    """Echoes like MockProvider for a trajectory run, but returns a fixed
    verdict for anything shaped like `audit_trajectories()`'s judge prompt
    -- recognized by content, not call order, so it stays correct
    regardless of how many trajectory runs precede the judge call."""

    name = "verdict-stub"

    def __init__(self, verdict_line: str = "VERDICT: CANDIDATE") -> None:
        self._verdict_line = verdict_line

    async def is_available(self) -> bool:
        return True

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if "ATTEMPT A (BASELINE)" in request.prompt:
            text = f"Attempt B is more complete.\n{self._verdict_line}"
        else:
            text = f"[stub reply] {request.prompt[:80]}"
        return CompletionResult(
            text=text, provider=self.name, model="stub", input_tokens=1, output_tokens=1
        )


async def test_run_skill_trajectory_prepends_the_skills_own_guidance(
    db_session: AsyncSession,
) -> None:
    skill = await register(db_session, FIXTURES / "sqlite-diagnostics")

    task = await run_skill_trajectory(
        db_session, MockProvider(), TelemetryRecorder(), skill, "check the tasks table"
    )

    run = (
        (await db_session.execute(select(TaskRun).where(TaskRun.task_id == task.id)))
        .scalars()
        .one()
    )
    steps = (
        (await db_session.execute(select(Step).where(Step.task_run_id == run.id))).scalars().all()
    )
    prompt_step = next(s for s in steps if s.name == "model.complete")
    assert "Use when a task involves inspecting or repairing" in prompt_step.payload["prompt"]
    assert "PRAGMA integrity_check" in prompt_step.payload["prompt"]
    assert "Objective: check the tasks table" in prompt_step.payload["prompt"]


async def test_audit_trajectories_with_mock_provider_is_an_honest_tie(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    # MockProvider has no real judgment capability -- a judge run through
    # it must never fabricate a confident verdict.
    baseline = await register(db_session, FIXTURES / "sqlite-diagnostics")
    candidate = await create_candidate_version(db_session, tmp_path, baseline, {})

    result = await audit_trajectories(
        db_session,
        MockProvider(),
        TelemetryRecorder(),
        baseline=baseline,
        candidate=candidate,
        objective="check the tasks table",
    )

    assert result.verdict is TrajectoryVerdict.TIE
    assert "did not include a parseable verdict" in result.rationale
    assert result.baseline_id == baseline.id
    assert result.candidate_id == candidate.id


async def test_audit_trajectories_records_two_real_task_trajectories(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline = await register(db_session, FIXTURES / "sqlite-diagnostics")
    candidate = await create_candidate_version(db_session, tmp_path, baseline, {})

    result = await audit_trajectories(
        db_session,
        MockProvider(),
        TelemetryRecorder(),
        baseline=baseline,
        candidate=candidate,
        objective="check the tasks table",
    )

    baseline_run = (
        (
            await db_session.execute(
                select(TaskRun).where(TaskRun.task_id == result.baseline_task_id)
            )
        )
        .scalars()
        .one()
    )
    candidate_run = (
        (
            await db_session.execute(
                select(TaskRun).where(TaskRun.task_id == result.candidate_task_id)
            )
        )
        .scalars()
        .one()
    )
    assert baseline_run.status is TaskStatus.COMPLETED
    assert candidate_run.status is TaskStatus.COMPLETED
    assert result.baseline_task_id != result.candidate_task_id


async def test_audit_trajectories_parses_a_real_verdict_from_the_judge(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    baseline = await register(db_session, FIXTURES / "sqlite-diagnostics")
    candidate = await create_candidate_version(db_session, tmp_path, baseline, {})

    result = await audit_trajectories(
        db_session,
        _VerdictProvider("VERDICT: CANDIDATE"),
        TelemetryRecorder(),
        baseline=baseline,
        candidate=candidate,
        objective="check the tasks table",
    )

    assert result.verdict is TrajectoryVerdict.CANDIDATE
    assert "VERDICT: CANDIDATE" in result.rationale


def test_parse_verdict_is_case_insensitive_and_ignores_surrounding_text() -> None:
    verdict, rationale = _parse_verdict("some reasoning...\nverdict: baseline\n")
    assert verdict is TrajectoryVerdict.BASELINE
    assert rationale


def test_parse_verdict_falls_back_to_tie_with_no_match() -> None:
    verdict, rationale = _parse_verdict("I have thoughts but no formatted answer.")
    assert verdict is TrajectoryVerdict.TIE
    assert "did not include a parseable verdict" in rationale


async def test_run_skill_trajectory_step_kind_is_recorded(db_session: AsyncSession) -> None:
    skill = await register(db_session, FIXTURES / "sqlite-diagnostics")

    task = await run_skill_trajectory(
        db_session, MockProvider(), TelemetryRecorder(), skill, "check the tasks table"
    )

    run = (
        (await db_session.execute(select(TaskRun).where(TaskRun.task_id == task.id)))
        .scalars()
        .one()
    )
    steps = (
        (await db_session.execute(select(Step).where(Step.task_run_id == run.id))).scalars().all()
    )
    assert any(s.kind is StepKind.OBSERVATION and s.name == "model.result" for s in steps)
