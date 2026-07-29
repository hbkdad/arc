"""Tests for acr.learning.self_practice."""

from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.topology import AgentTopologyRecord
from acr.learning.self_practice import run_self_practice
from acr.providers.mock import MockProvider
from acr.skills.models import SkillStatus
from acr.skills.registry import register, set_status

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


async def test_runs_a_practice_task_for_each_active_skill_with_applicability(
    db_session: AsyncSession,
) -> None:
    skill = await register(db_session, FIXTURES / "sqlite-diagnostics")
    skill = await set_status(db_session, skill.id, SkillStatus.ACTIVE)
    await db_session.commit()

    runs = await run_self_practice(db_session, MockProvider())

    assert len(runs) == 1
    assert runs[0].skill_id == skill.id
    assert runs[0].objective == skill.applicability
    assert runs[0].task_class == skill.task_classes[0]
    assert runs[0].task.status.value == "completed"
    assert runs[0].review.passed is True


async def test_records_real_skill_reliability_and_topology_evidence(
    db_session: AsyncSession,
) -> None:
    skill = await register(db_session, FIXTURES / "sqlite-diagnostics")
    skill = await set_status(db_session, skill.id, SkillStatus.ACTIVE)
    await db_session.commit()

    await run_self_practice(db_session, MockProvider())

    await db_session.refresh(skill)
    assert skill.successful_uses == 1

    rows = (
        (
            await db_session.execute(
                select(AgentTopologyRecord).where(
                    AgentTopologyRecord.task_class == skill.task_classes[0]
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_skips_a_skill_with_no_declared_task_classes(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    manifest = yaml.safe_load((FIXTURES / "sqlite-diagnostics" / "SKILL.yaml").read_text())
    manifest["id"] = "no-task-classes"
    manifest["task_classes"] = []
    skill_dir = tmp_path / "no-task-classes"
    skill_dir.mkdir()
    (skill_dir / "SKILL.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    await register(db_session, skill_dir)
    await set_status(db_session, "no-task-classes", SkillStatus.ACTIVE)
    await db_session.commit()

    runs = await run_self_practice(db_session, MockProvider())

    assert runs == []


async def test_skips_a_non_active_skill(db_session: AsyncSession) -> None:
    await register(db_session, FIXTURES / "sqlite-diagnostics")
    await db_session.commit()  # left in the default EXPERIMENTAL status

    runs = await run_self_practice(db_session, MockProvider())

    assert runs == []


async def test_limit_caps_how_many_skills_practice(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    manifest = yaml.safe_load((FIXTURES / "sqlite-diagnostics" / "SKILL.yaml").read_text())
    for i in range(3):
        variant = dict(manifest)
        variant["id"] = f"practice-skill-{i}"
        skill_dir = tmp_path / f"practice-skill-{i}"
        skill_dir.mkdir()
        (skill_dir / "SKILL.yaml").write_text(yaml.safe_dump(variant), encoding="utf-8")
        await register(db_session, skill_dir)
        await set_status(db_session, f"practice-skill-{i}", SkillStatus.ACTIVE)
    await db_session.commit()

    runs = await run_self_practice(db_session, MockProvider(), limit=2)

    assert len(runs) == 2


async def test_returns_empty_list_with_no_active_skills(db_session: AsyncSession) -> None:
    runs = await run_self_practice(db_session, MockProvider())

    assert runs == []
