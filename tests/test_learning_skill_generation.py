"""Tests for acr.learning.skill_generation (master §697-716)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.execution import run_task
from acr.core.tasks.models import TaskStatus
from acr.learning.skill_generation import (
    detect_repeated_successes,
    generate_candidate_skill,
)
from acr.providers.mock import MockProvider
from acr.skills.models import SkillStatus
from acr.skills.registry import set_status
from acr.telemetry.recorder import TelemetryRecorder


async def test_detect_repeated_successes_requires_the_minimum_count(
    db_session: AsyncSession,
) -> None:
    for _ in range(2):
        task = await run_task(db_session, "repeat me", MockProvider(), TelemetryRecorder())
        assert task.status is TaskStatus.COMPLETED

    patterns = await detect_repeated_successes(db_session, min_repeats=3)
    assert patterns == []

    patterns = await detect_repeated_successes(db_session, min_repeats=2)
    assert len(patterns) == 1
    assert patterns[0].objective == "repeat me"
    assert patterns[0].occurrences == 2


async def test_detect_repeated_successes_ignores_distinct_objectives(
    db_session: AsyncSession,
) -> None:
    await run_task(db_session, "objective A", MockProvider(), TelemetryRecorder())
    await run_task(db_session, "objective B", MockProvider(), TelemetryRecorder())

    patterns = await detect_repeated_successes(db_session, min_repeats=2)
    assert patterns == []


async def test_generate_candidate_skill_writes_a_real_manifest_and_quarantines(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    for _ in range(3):
        await run_task(db_session, "diagnose the sqlite index", MockProvider(), TelemetryRecorder())

    patterns = await detect_repeated_successes(db_session, min_repeats=3)
    assert len(patterns) == 1

    record = await generate_candidate_skill(db_session, tmp_path, patterns[0])
    await db_session.commit()

    assert record.status is SkillStatus.QUARANTINED
    assert record.origin == "generated"

    manifest_path = tmp_path / "generated_skills" / record.id / "SKILL.yaml"
    assert manifest_path.is_file()
    assert "diagnose the sqlite index" in manifest_path.read_text(encoding="utf-8")


async def test_generate_candidate_skill_is_idempotent_across_reruns(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    for _ in range(3):
        await run_task(db_session, "diagnose the sqlite index", MockProvider(), TelemetryRecorder())
    patterns = await detect_repeated_successes(db_session, min_repeats=3)

    first = await generate_candidate_skill(db_session, tmp_path, patterns[0])
    await db_session.commit()
    assert first.status is SkillStatus.QUARANTINED

    # Re-running generation for the same pattern must not crash trying to
    # re-transition an already-quarantined skill.
    second = await generate_candidate_skill(db_session, tmp_path, patterns[0])
    await db_session.commit()
    assert second.id == first.id
    assert second.status is SkillStatus.QUARANTINED


async def test_generate_candidate_skill_does_not_reclaim_an_activated_skill(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    for _ in range(3):
        await run_task(db_session, "diagnose the sqlite index", MockProvider(), TelemetryRecorder())
    patterns = await detect_repeated_successes(db_session, min_repeats=3)

    first = await generate_candidate_skill(db_session, tmp_path, patterns[0])
    await set_status(db_session, first.id, SkillStatus.ACTIVE)

    # A human already activated it — regenerating must not silently
    # re-quarantine a skill someone reviewed and trusted.
    second = await generate_candidate_skill(db_session, tmp_path, patterns[0])
    assert second.status is SkillStatus.ACTIVE
