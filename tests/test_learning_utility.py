"""Tests for acr.learning.utility."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.learning.utility import record_skill_outcome
from acr.skills.registry import SkillNotFoundError, register

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


async def test_record_skill_outcome_raises_for_unknown_skill(db_session: AsyncSession) -> None:
    with pytest.raises(SkillNotFoundError):
        await record_skill_outcome(db_session, "does-not-exist", True)


async def test_record_skill_outcome_updates_reliability(db_session: AsyncSession) -> None:
    record = await register(db_session, FIXTURES / "sqlite-diagnostics")
    assert record.reliability == 0.0

    record = await record_skill_outcome(db_session, record.id, True)
    assert record.successful_uses == 1
    assert record.failed_uses == 0
    assert record.reliability == 1.0

    record = await record_skill_outcome(db_session, record.id, False)
    assert record.successful_uses == 1
    assert record.failed_uses == 1
    assert record.reliability == 0.5
