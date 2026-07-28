"""Tests for acr.skills.routing (master §685-696)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.skills.models import SkillRecord, SkillStatus
from acr.skills.routing import route


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
