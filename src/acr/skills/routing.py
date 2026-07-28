"""Skill routing (master §685-696).

For each task: classify -> retrieve candidates -> estimate applicability ->
estimate expected quality gain -> estimate token overhead -> check prior
performance -> remove overlapping skills -> choose the smallest useful set.

Only `active` skills are ever routed to — experimental/quarantined skills
exist for review, not dispatch (master §679-682 statuses; §336-343 of the
reference safety boundary language is the same principle: untrusted skills
don't run automatically).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from acr.skills.models import SkillRecord, SkillStatus
from acr.skills.registry import list_skills
from acr.skills.search import search


@dataclass(frozen=True, slots=True)
class RoutedSkill:
    record: SkillRecord
    applicability: float
    expected_quality_gain: float
    token_overhead: int
    selection_reason: str


def _applicability(
    record: SkillRecord, task_class: str | None, keyword_rank: float | None
) -> float:
    """0..1 estimate of fit: keyword relevance plus an exact task_class match bonus.

    A task_class match must surface a skill even with zero keyword overlap
    between the task description and the skill's own description — that's
    why candidacy (below) is never gated on a keyword hit.
    """
    keyword_score = 1.0 / (1.0 + keyword_rank) if keyword_rank is not None else 0.0
    class_score = 1.0 if task_class is not None and task_class in record.task_classes else 0.0
    return max(keyword_score, class_score)


def _remove_overlapping(candidates: list[RoutedSkill]) -> list[RoutedSkill]:
    """Drop skills that overlap in task_classes with an already-kept, better-scored skill."""
    kept: list[RoutedSkill] = []
    covered_classes: set[str] = set()
    for candidate in sorted(candidates, key=lambda c: c.expected_quality_gain, reverse=True):
        classes = set(candidate.record.task_classes)
        if classes and classes <= covered_classes:
            continue
        kept.append(candidate)
        covered_classes |= classes
    return kept


async def route(
    session: AsyncSession,
    task_description: str,
    *,
    task_class: str | None = None,
    max_skills: int = 3,
) -> list[RoutedSkill]:
    """Route `task_description` to the smallest useful set of active skills."""
    # 1. CLASSIFY: `task_class`, if given by the caller — no classifier model
    #    exists yet, so an unclassified task just relies on keyword matching.

    # 2. RETRIEVE CANDIDATES: every active skill is a candidate; keyword
    # search supplies a relevance signal but never gates candidacy (a
    # task_class match must surface a skill even with zero keyword overlap).
    active_skills = await list_skills(session, status=SkillStatus.ACTIVE)
    keyword_hits = await search(session, task_description, status=SkillStatus.ACTIVE, limit=20)
    keyword_ranks = {hit.record.id: hit.rank for hit in keyword_hits}

    candidates: list[RoutedSkill] = []
    for record in active_skills:
        # 3. ESTIMATE APPLICABILITY
        applicability = _applicability(record, task_class, keyword_ranks.get(record.id))
        if applicability <= 0:
            continue

        # 4. ESTIMATE EXPECTED QUALITY GAIN + 6. CHECK PRIOR PERFORMANCE:
        #    reliability *is* prior performance — it is exactly the
        #    successful/total ratio a skill has earned in production use.
        expected_quality_gain = applicability * (0.5 + 0.5 * record.reliability)

        # 5. ESTIMATE TOKEN OVERHEAD
        token_overhead = record.token_estimate

        candidates.append(
            RoutedSkill(
                record=record,
                applicability=applicability,
                expected_quality_gain=expected_quality_gain,
                token_overhead=token_overhead,
                selection_reason=(
                    f"applicability={applicability:.2f} reliability={record.reliability:.2f} "
                    f"tokens={token_overhead}"
                ),
            )
        )

    # 7. REMOVE OVERLAPPING SKILLS
    candidates = _remove_overlapping(candidates)

    # 8. CHOOSE THE SMALLEST USEFUL SET
    candidates.sort(key=lambda c: c.expected_quality_gain, reverse=True)
    return candidates[:max_skills]
