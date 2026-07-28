"""Tests for acr.skills.registry (master §645-683)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.skills.models import InvalidSkillTransition, SkillStatus
from acr.skills.registry import SkillNotFoundError, get, list_skills, register, set_status

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


async def test_register_creates_a_new_experimental_record(db_session: AsyncSession) -> None:
    record = await register(db_session, FIXTURES / "sqlite-diagnostics")

    assert record.id == "sqlite-diagnostics"
    assert record.status is SkillStatus.EXPERIMENTAL
    assert record.reliability == 0.0


async def test_register_is_idempotent_and_preserves_status(db_session: AsyncSession) -> None:
    first = await register(db_session, FIXTURES / "sqlite-diagnostics")
    await set_status(db_session, first.id, SkillStatus.ACTIVE)

    second = await register(db_session, FIXTURES / "sqlite-diagnostics")

    assert second.id == first.id
    assert second.status is SkillStatus.ACTIVE  # re-registering doesn't reset activation


async def test_get_returns_none_for_unknown_id(db_session: AsyncSession) -> None:
    assert await get(db_session, "does-not-exist") is None


async def test_list_skills_filters_by_status(db_session: AsyncSession) -> None:
    record = await register(db_session, FIXTURES / "sqlite-diagnostics")
    await set_status(db_session, record.id, SkillStatus.ACTIVE)

    active = await list_skills(db_session, status=SkillStatus.ACTIVE)
    experimental = await list_skills(db_session, status=SkillStatus.EXPERIMENTAL)

    assert [r.id for r in active] == [record.id]
    assert experimental == []


async def test_set_status_raises_for_unknown_skill(db_session: AsyncSession) -> None:
    with pytest.raises(SkillNotFoundError):
        await set_status(db_session, "does-not-exist", SkillStatus.ACTIVE)


async def test_set_status_rejects_invalid_transition(db_session: AsyncSession) -> None:
    record = await register(db_session, FIXTURES / "sqlite-diagnostics")
    assert record.status is SkillStatus.EXPERIMENTAL

    with pytest.raises(InvalidSkillTransition):
        await set_status(db_session, record.id, SkillStatus.RETIRED)


async def test_full_lifecycle_experimental_to_active_to_deprecated_to_retired(
    db_session: AsyncSession,
) -> None:
    record = await register(db_session, FIXTURES / "sqlite-diagnostics")

    record = await set_status(db_session, record.id, SkillStatus.ACTIVE)
    assert record.status is SkillStatus.ACTIVE

    record = await set_status(db_session, record.id, SkillStatus.DEPRECATED)
    assert record.status is SkillStatus.DEPRECATED

    record = await set_status(db_session, record.id, SkillStatus.RETIRED)
    assert record.status is SkillStatus.RETIRED
