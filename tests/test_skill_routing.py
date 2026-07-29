"""Tests for acr.skills.routing (master §685-696)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.skills.models import SkillRecord, SkillStatus
from acr.skills.routing import _applicability, route


async def _make_skill(
    session: AsyncSession,
    skill_id: str,
    *,
    name: str,
    description: str,
    task_classes: list[str],
    reliability: float,
    token_estimate: int = 100,
    status: SkillStatus = SkillStatus.ACTIVE,
) -> SkillRecord:
    record = SkillRecord(
        id=skill_id,
        name=name,
        version="1.0.0",
        description=description,
        task_classes=task_classes,
        path=f"/skills/{skill_id}",
        status=status,
        reliability=reliability,
        token_estimate=token_estimate,
    )
    session.add(record)
    await session.flush()
    return record


async def test_route_only_considers_active_skills(db_session: AsyncSession) -> None:
    await _make_skill(
        db_session,
        "experimental-one",
        name="Experimental",
        description="Diagnose SQLite database integrity issues.",
        task_classes=["database-diagnostics"],
        reliability=0.9,
        status=SkillStatus.EXPERIMENTAL,
    )

    routed = await route(db_session, "Diagnose SQLite database integrity issues")

    assert routed == []


async def test_route_ranks_by_expected_quality_gain(db_session: AsyncSession) -> None:
    await _make_skill(
        db_session,
        "low-reliability",
        name="Low Reliability",
        description="Diagnose SQLite database integrity issues.",
        task_classes=["database-diagnostics"],
        reliability=0.1,
    )
    await _make_skill(
        db_session,
        "high-reliability",
        name="High Reliability",
        description="Diagnose SQLite database integrity issues.",
        task_classes=["database-migration"],
        reliability=0.9,
    )

    routed = await route(db_session, "Diagnose SQLite database integrity issues")

    assert [r.record.id for r in routed] == ["high-reliability", "low-reliability"]


async def test_route_removes_overlapping_skills(db_session: AsyncSession) -> None:
    await _make_skill(
        db_session,
        "better",
        name="Better",
        description="Diagnose SQLite database integrity issues thoroughly.",
        task_classes=["database-diagnostics"],
        reliability=0.9,
    )
    await _make_skill(
        db_session,
        "worse-overlapping",
        name="Worse",
        description="Diagnose SQLite database integrity issues briefly.",
        task_classes=["database-diagnostics"],
        reliability=0.2,
    )

    routed = await route(db_session, "Diagnose SQLite database integrity issues")

    assert [r.record.id for r in routed] == ["better"]


async def test_route_respects_max_skills(db_session: AsyncSession) -> None:
    for i in range(5):
        await _make_skill(
            db_session,
            f"skill-{i}",
            name=f"Skill {i}",
            description="Diagnose SQLite database integrity issues.",
            task_classes=[f"class-{i}"],
            reliability=0.5,
        )

    routed = await route(db_session, "Diagnose SQLite database integrity issues", max_skills=2)

    assert len(routed) == 2


def test_applicability_stays_positive_for_a_strong_bm25_match_with_no_class_match() -> None:
    # A real SQLite bm25() rank this negative is routine once a table holds
    # a few hundred rows (bm25 grows more negative, not more positive, with
    # match strength and corpus size). The old `1.0 / (1.0 + rank)` formula
    # went negative once rank < -1, which `route()` then clips to 0 via
    # `if applicability <= 0: continue` -- silently dropping a genuinely
    # relevant skill from candidacy the longer ACR runs. task_class=None
    # forces class_score to 0, isolating the keyword-only path.
    record = SkillRecord(
        id="strong-match",
        name="Strong Match",
        version="1.0.0",
        description="Diagnose SQLite database integrity issues.",
        task_classes=[],
        path="/skills/strong-match",
        status=SkillStatus.ACTIVE,
        reliability=0.5,
        token_estimate=100,
    )

    applicability = _applicability(record, task_class=None, keyword_rank=-15.7)

    assert applicability > 0


async def test_route_task_class_bonus_matches_even_without_keyword_overlap(
    db_session: AsyncSession,
) -> None:
    await _make_skill(
        db_session,
        "class-matched",
        name="Class Matched",
        description="Completely unrelated wording with no shared keywords.",
        task_classes=["database-diagnostics"],
        reliability=0.5,
    )

    routed = await route(db_session, "fix the sqlite index", task_class="database-diagnostics")

    assert [r.record.id for r in routed] == ["class-matched"]
