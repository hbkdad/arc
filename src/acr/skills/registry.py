"""Skill registry (master §645-683).

`register()` is idempotent per manifest `id`: re-registering an already
registered skill updates its metadata from the manifest but preserves its
`status`, `reliability`, and use counters — activation state is earned, not
reset by re-reading a file.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.security.safe_mode import require_not_safe_mode
from acr.skills.format import SkillManifest, load_manifest
from acr.skills.models import SkillRecord, SkillStatus


async def register(session: AsyncSession, skill_dir: Path) -> SkillRecord:
    """Load `SKILL.yaml` from `skill_dir` and register (or update) it."""
    manifest = load_manifest(skill_dir)
    existing = await session.get(SkillRecord, manifest.id)

    if existing is not None:
        _apply_manifest(existing, manifest, skill_dir)
        await session.flush()
        return existing

    record = SkillRecord(id=manifest.id, path=str(skill_dir), status=SkillStatus.EXPERIMENTAL)
    _apply_manifest(record, manifest, skill_dir)
    session.add(record)
    await session.flush()
    return record


def _apply_manifest(record: SkillRecord, manifest: SkillManifest, skill_dir: Path) -> None:
    record.name = manifest.name
    record.version = manifest.version
    record.description = manifest.description
    record.task_classes = manifest.task_classes
    record.inputs = manifest.inputs
    record.outputs = manifest.outputs
    record.dependencies = manifest.dependencies
    record.permissions = manifest.permissions
    record.tools = manifest.tools
    record.models = manifest.models
    record.token_estimate = manifest.token_estimate
    record.applicability = manifest.applicability
    record.contraindications = manifest.contraindications
    record.verification = manifest.verification
    record.origin = manifest.origin
    record.author = manifest.author
    record.path = str(skill_dir)


async def get(session: AsyncSession, skill_id: str) -> SkillRecord | None:
    return await session.get(SkillRecord, skill_id)


async def list_skills(
    session: AsyncSession, *, status: SkillStatus | None = None
) -> list[SkillRecord]:
    stmt = select(SkillRecord).order_by(SkillRecord.name)
    if status is not None:
        stmt = stmt.where(SkillRecord.status == status)
    return list((await session.execute(stmt)).scalars().all())


class SkillNotFoundError(LookupError):
    """Raised when a lifecycle action targets an unknown skill id."""


async def set_status(
    session: AsyncSession, skill_id: str, target: SkillStatus, *, safe_mode: bool = False
) -> SkillRecord:
    """Manual activation/lifecycle control (master §1661: "manual activation").

    A thin, validated wrapper over `SkillRecord.transition` — raises
    `SkillNotFoundError` for an unknown id, `InvalidSkillTransition` (from
    `acr.skills.models`) for a disallowed transition, and `SafeModeError`
    (master §1534-1550: safe mode disables skill activation) if `safe_mode`
    is set and `target` is ACTIVE.
    """
    if target is SkillStatus.ACTIVE:
        require_not_safe_mode(safe_mode, f"skill.activate:{skill_id}")
    record = await get(session, skill_id)
    if record is None:
        raise SkillNotFoundError(skill_id)
    record.transition(target)
    await session.flush()
    return record
