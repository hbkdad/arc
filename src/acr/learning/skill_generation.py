"""Candidate skill generation (master §697-716).

"Generate candidate skills when: the same successful procedure repeats..."
— detected here as the same task objective completing successfully often
enough. A detected pattern is materialized as a real `SKILL.yaml` package
under the data directory, registered through the normal registry path
(`acr.skills.registry.register`), then explicitly quarantined (master §704:
"Generated skills begin in quarantine") — never active, never trusted until
Phase 9's validation pipeline exists.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.tasks.models import Task, TaskStatus
from acr.skills.models import SkillRecord, SkillStatus
from acr.skills.registry import register, set_status

DEFAULT_MIN_REPEATS = 3
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class RepeatedPattern:
    objective: str
    occurrences: int
    task_ids: list[str]


async def detect_repeated_successes(
    session: AsyncSession, *, min_repeats: int = DEFAULT_MIN_REPEATS
) -> list[RepeatedPattern]:
    """Objectives that have completed successfully at least `min_repeats` times."""
    stmt = select(Task).where(Task.status == TaskStatus.COMPLETED)
    tasks = (await session.execute(stmt)).scalars().all()

    by_objective: dict[str, list[Task]] = defaultdict(list)
    for task in tasks:
        by_objective[task.objective].append(task)

    return [
        RepeatedPattern(objective=objective, occurrences=len(group), task_ids=[t.id for t in group])
        for objective, group in by_objective.items()
        if len(group) >= min_repeats
    ]


def _slugify(text: str) -> str:
    slug = _SLUG_PATTERN.sub("-", text.lower()).strip("-")
    return slug[:50] or "generated-skill"


async def generate_candidate_skill(
    session: AsyncSession, data_dir: Path, pattern: RepeatedPattern
) -> SkillRecord:
    """Write a real SKILL.yaml for `pattern`, register it, and quarantine it."""
    skill_id = f"generated-{_slugify(pattern.objective)}"
    skill_dir = data_dir / "generated_skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "id": skill_id,
        "name": pattern.objective[:80],
        "version": "0.1.0",
        "description": (
            f"Auto-generated from {pattern.occurrences} repeated successful "
            f"completions of: {pattern.objective}"
        ),
        "task_classes": [],
        "origin": "generated",
        "author": "acr.learning.skill_generation",
        "applicability": (
            f"Repeats the objective {pattern.objective!r}, which has succeeded "
            f"{pattern.occurrences} times."
        ),
        "verification": "Not yet validated — quarantined pending Phase 9 skill validation.",
    }
    (skill_dir / "SKILL.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )

    record = await register(session, skill_dir)
    if record.status is SkillStatus.EXPERIMENTAL:
        # Freshly generated: master §704 says quarantine, not experimental.
        # A record already past EXPERIMENTAL (re-run, or a human already
        # reviewed it) keeps whatever status it earned — generation must
        # not silently re-quarantine a skill someone already activated.
        record = await set_status(session, record.id, SkillStatus.QUARANTINED)
    return record
