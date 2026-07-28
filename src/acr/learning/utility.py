"""Utility updates (master §463, §676, §696: track whether a routed skill
actually helped).

Mirrors `acr.context.attribution`'s memory utility update for
`SkillRecord` — closes a Phase 4 gap where `successful_uses`/`failed_uses`/
`reliability` existed as columns but nothing ever wrote to them, so
`routing.route()`'s "check prior performance" step always saw `0.0`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.skills.models import SkillRecord
from acr.skills.registry import SkillNotFoundError, get


async def record_skill_outcome(session: AsyncSession, skill_id: str, success: bool) -> SkillRecord:
    """Record whether a routed skill's use succeeded, updating `reliability`."""
    record = await get(session, skill_id)
    if record is None:
        raise SkillNotFoundError(skill_id)

    if success:
        record.successful_uses += 1
    else:
        record.failed_uses += 1
    total = record.successful_uses + record.failed_uses
    record.reliability = record.successful_uses / total if total else 0.0

    await session.flush()
    return record
