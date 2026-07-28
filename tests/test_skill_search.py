"""Tests for acr.skills.search."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from acr.skills.models import SkillStatus
from acr.skills.registry import register, set_status
from acr.skills.search import search

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


async def test_search_finds_registered_skill_by_keyword(db_session: AsyncSession) -> None:
    await register(db_session, FIXTURES / "sqlite-diagnostics")

    results = await search(db_session, "SQLite diagnostics")

    assert len(results) == 1
    assert results[0].record.id == "sqlite-diagnostics"


async def test_search_returns_nothing_for_unrelated_query(db_session: AsyncSession) -> None:
    await register(db_session, FIXTURES / "sqlite-diagnostics")

    results = await search(db_session, "kubernetes networking")

    assert results == []


async def test_search_can_filter_by_status(db_session: AsyncSession) -> None:
    record = await register(db_session, FIXTURES / "sqlite-diagnostics")

    experimental_results = await search(db_session, "SQLite", status=SkillStatus.EXPERIMENTAL)
    active_results = await search(db_session, "SQLite", status=SkillStatus.ACTIVE)
    assert len(experimental_results) == 1
    assert active_results == []

    await set_status(db_session, record.id, SkillStatus.ACTIVE)
    active_results = await search(db_session, "SQLite", status=SkillStatus.ACTIVE)
    assert len(active_results) == 1
