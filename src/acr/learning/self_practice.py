"""Scheduled self-practice: grow real reliability/topology evidence at
volume without external users, by running each active skill's own
declared applicability through the real `agents.factory.spawn_agent()`
path (master principle #22: no unevidenced claims -- every run is a
genuine task execution, reviewed the same way any other spawn is, not a
synthetic score).

The "objective" for each practice run is the skill's own author-written
`applicability` field ("Use when a task involves X"), not a fabricated
scenario -- it's the one thing already on record describing when the
skill should be used, so exercising it there is grounded in real
metadata rather than invention. A skill with no declared task_classes or
empty applicability is skipped, not padded with a made-up one.

"Scheduled" describes the intended use (wire `acr learn self-practice`
into cron/Task Scheduler yourself), not something this module installs
on its own -- modifying the host's own scheduler is a system-level change
outside what a library/CLI command does as a side effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from acr.providers.base import ModelProvider
from acr.skills.models import SkillStatus
from acr.skills.registry import list_skills
from acr.telemetry.recorder import TelemetryRecorder

if TYPE_CHECKING:
    from acr.core.tasks.models import Task
    from acr.evaluation.panel import PanelResult

__all__ = ["PracticeRun", "run_self_practice"]


@dataclass(frozen=True, slots=True)
class PracticeRun:
    skill_id: str
    task_class: str
    objective: str
    task: Task
    review: PanelResult


async def run_self_practice(
    session: AsyncSession, provider: ModelProvider, *, limit: int | None = None
) -> list[PracticeRun]:
    """Run every active skill's own `applicability` text as a real
    objective for its first declared task_class, through the same
    evidence-recording path `agents spawn` uses -- skill reliability and
    topology history both accrue for real, not simulated."""
    # Deferred: acr.agents.factory itself imports acr.learning.utility, so
    # a module-level import here would be circular whenever something
    # reaches acr.agents.factory before acr.learning has finished
    # initializing (e.g. conftest.py importing acr.agents.topology first).
    # By the time this function actually runs, both packages are long done
    # initializing.
    from acr.agents.factory import spawn_agent
    from acr.agents.planner import plan_agent

    skills = await list_skills(session, status=SkillStatus.ACTIVE)
    if limit is not None:
        skills = skills[:limit]

    runs: list[PracticeRun] = []
    for skill in skills:
        if not skill.task_classes or not skill.applicability.strip():
            continue
        task_class = skill.task_classes[0]
        objective = skill.applicability
        spec = await plan_agent(session, objective, task_class=task_class)
        task, review = await spawn_agent(
            session, spec, provider, TelemetryRecorder(), task_class=task_class, force=True
        )
        runs.append(
            PracticeRun(
                skill_id=skill.id,
                task_class=task_class,
                objective=objective,
                task=task,
                review=review,
            )
        )
    return runs
