"""Regression guard for the real, shipped skill packages under `skills/`.

These aren't test fixtures -- they're first-party ACR skills meant to
actually be registered and routed to. A manifest referencing a capability
or tool name that later drifts (e.g. renamed in `acr.security.permissions`
or `acr.tools.default_tools`) would otherwise fail silently: `acr skills
register` doesn't validate, so the breakage would only surface the next
time someone happened to run `acr skills validate --check-tools` by hand.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.skills.registry import register
from acr.skills.validation import run_validation
from acr.tools.default_tools import build_default_registry

SKILLS_DIR = Path(__file__).parent.parent / "skills"
SKILL_DIRS = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()) if SKILLS_DIR.is_dir() else []


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
async def test_shipped_skill_passes_validation(skill_dir: Path, db_session: AsyncSession) -> None:
    record = await register(db_session, skill_dir)
    report = await run_validation(db_session, record, tool_registry=build_default_registry())
    failed = [s.name for s in report.stages if s.status.value == "failed"]
    assert report.passed, f"{skill_dir.name} failed stages: {failed}"


def test_at_least_one_shipped_skill_exists() -> None:
    assert SKILL_DIRS, "skills/ should contain at least one real, first-party skill package"
