"""Paired trajectory auditing for skill evolution.

`acr.evaluation.evaluators`' own module docstring names this the missing
piece: "an LLM-judge evaluator later once there's a real model call to
grade." `skills.evolution.compare_versions()` only compares two aggregate
numbers (`reliability`, `token_estimate`) computed from *historical* usage
— a freshly evolved candidate has no usage history yet, so that
comparison alone can only ever measure the baseline against nothing.

This module generates real evidence at comparison time instead: run the
same objective through the baseline and the candidate (`applicability` +
`instructions` prepended to it -- the first place a skill's own content
actually shapes a task's real output; previously nothing did, skills were
only ever scored *after the fact* via `learning.utility.record_skill_outcome()`),
then have a real LLM judge compare the two resulting trajectories head to
head. This is the SkillAudit research pattern cited in this session's
competitive-research pass: pairwise relative judgment between two real
runs, not an absolute score against a fixed threshold.

Only as good as the provider judging it -- `MockProvider`'s deterministic
echo can't produce real judgment, so a judge run through it correctly
comes back `TIE` with "no parseable verdict" every time. A configured
cloud/Ollama provider (see the dashboard's `/settings` page) is what
makes this evidence real rather than a placeholder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.execution import run_task
from acr.core.tasks.models import Step, StepKind, Task, TaskRun
from acr.providers.base import CompletionRequest, ModelProvider
from acr.skills.format import load_instructions, load_manifest
from acr.skills.models import SkillRecord
from acr.telemetry.recorder import TelemetryRecorder

__all__ = [
    "TrajectoryAuditResult",
    "TrajectoryVerdict",
    "audit_trajectories",
    "run_skill_trajectory",
]

_VERDICT_PATTERN = re.compile(r"VERDICT:\s*(BASELINE|CANDIDATE|TIE)", re.IGNORECASE)


class TrajectoryVerdict(StrEnum):
    BASELINE = "baseline"
    CANDIDATE = "candidate"
    TIE = "tie"


def _skill_prompt(*, applicability: str, instructions: str, objective: str) -> str:
    parts = [p for p in (applicability.strip(), instructions.strip()) if p]
    guidance = "\n\n".join(parts)
    if not guidance:
        return objective
    return f"{guidance}\n\nObjective: {objective}"


async def run_skill_trajectory(
    session: AsyncSession,
    provider: ModelProvider,
    telemetry: TelemetryRecorder,
    skill: SkillRecord,
    objective: str,
) -> Task:
    """Run `objective` guided by `skill`'s own applicability + instructions
    -- a real `run_task()` call, so the resulting `Task` is a genuine
    trajectory (real Steps, real telemetry), not a simulation."""
    skill_dir = Path(skill.path)
    manifest = load_manifest(skill_dir)
    instructions = load_instructions(skill_dir) or ""
    prompt = _skill_prompt(
        applicability=manifest.applicability, instructions=instructions, objective=objective
    )
    return await run_task(session, prompt, provider, telemetry)


async def _final_output_text(session: AsyncSession, task: Task) -> str:
    # Ordered defensively, not because run_task() produces more than one
    # TaskRun/relevant Step today (it doesn't -- one run, one OBSERVATION
    # step, a hard try/except fork) -- but silently returning stale output
    # if that ever changes (e.g. a future retry path) would be a much
    # worse failure mode than a query hint that's momentarily redundant.
    run = (
        (
            await session.execute(
                select(TaskRun)
                .where(TaskRun.task_id == task.id)
                .order_by(TaskRun.started_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if run is None:
        return ""
    steps = (
        (await session.execute(select(Step).where(Step.task_run_id == run.id).order_by(Step.index)))
        .scalars()
        .all()
    )
    for step in steps:
        if step.kind is StepKind.OBSERVATION and step.name == "model.result":
            text = step.payload.get("text")
            return text if isinstance(text, str) else ""
        if step.kind is StepKind.OBSERVATION and step.name == "model.error":
            error = step.payload.get("error")
            return f"(failed: {error})" if isinstance(error, str) else "(failed)"
    return ""


@dataclass(frozen=True, slots=True)
class TrajectoryAuditResult:
    baseline_id: str
    candidate_id: str
    baseline_task_id: str
    candidate_task_id: str
    objective: str
    verdict: TrajectoryVerdict
    rationale: str


def _judge_prompt(*, objective: str, baseline_output: str, candidate_output: str) -> str:
    return (
        "You are comparing two attempts at the same objective, produced by two "
        "versions of the same instructions. Judge which attempt better achieves "
        "the objective -- correctness and completeness first, then clarity and "
        "efficiency. If they are genuinely equivalent, say so.\n\n"
        f"OBJECTIVE: {objective}\n\n"
        f"ATTEMPT A (BASELINE):\n{baseline_output}\n\n"
        f"ATTEMPT B (CANDIDATE):\n{candidate_output}\n\n"
        "End your response with exactly one line in the form "
        "'VERDICT: BASELINE', 'VERDICT: CANDIDATE', or 'VERDICT: TIE'."
    )


def _parse_verdict(judge_text: str) -> tuple[TrajectoryVerdict, str]:
    # The LAST match, not the first: the judge prompt embeds both attempts'
    # raw text, and a real model can echo/quote the instruction text (which
    # itself contains all three verdict strings) before its own genuine
    # closing line -- taking the first match would misreport in exactly
    # that case.
    matches = list(_VERDICT_PATTERN.finditer(judge_text))
    if not matches:
        return TrajectoryVerdict.TIE, "judge response did not include a parseable verdict"
    return TrajectoryVerdict(matches[-1].group(1).lower()), judge_text.strip()


async def audit_trajectories(
    session: AsyncSession,
    provider: ModelProvider,
    telemetry: TelemetryRecorder,
    *,
    baseline: SkillRecord,
    candidate: SkillRecord,
    objective: str,
) -> TrajectoryAuditResult:
    """Run `baseline` and `candidate` on the same `objective`, then have
    `provider` judge the two resulting trajectories head to head. Every
    step -- both trajectory runs and the judge call -- is a real
    `provider.complete()`, so the same `provider` is reused throughout:
    asking a stronger model to judge a weaker model's own two attempts
    would conflate "which provider is smarter" with "which skill version
    is better," the actual question being asked here.
    """
    baseline_task = await run_skill_trajectory(session, provider, telemetry, baseline, objective)
    candidate_task = await run_skill_trajectory(session, provider, telemetry, candidate, objective)

    baseline_output = await _final_output_text(session, baseline_task)
    candidate_output = await _final_output_text(session, candidate_task)

    judge_result = await provider.complete(
        CompletionRequest(
            prompt=_judge_prompt(
                objective=objective,
                baseline_output=baseline_output,
                candidate_output=candidate_output,
            )
        )
    )
    verdict, rationale = _parse_verdict(judge_result.text)

    return TrajectoryAuditResult(
        baseline_id=baseline.id,
        candidate_id=candidate.id,
        baseline_task_id=baseline_task.id,
        candidate_task_id=candidate_task.id,
        objective=objective,
        verdict=verdict,
        rationale=rationale,
    )
