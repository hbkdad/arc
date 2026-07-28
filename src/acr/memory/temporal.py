"""Temporal memory queries (master §577-591).

Facts change; history is preserved via `supersedes`/`superseded_by` and
`valid_from`/`valid_until` rather than deletion (master §583-584).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory.models import MemoryRecord, MemoryStatus


async def current(session: AsyncSession, subject: str) -> MemoryRecord | None:
    """The presently valid memory record for `subject`, if any."""
    stmt = (
        select(MemoryRecord)
        .where(MemoryRecord.subject == subject)
        .where(MemoryRecord.status == MemoryStatus.CONFIRMED)
        .where(MemoryRecord.valid_until.is_(None))
        .order_by(MemoryRecord.valid_from.desc())
    )
    return (await session.execute(stmt)).scalars().first()


async def at(session: AsyncSession, subject: str, timestamp: datetime) -> MemoryRecord | None:
    """The memory record for `subject` that was valid at `timestamp`."""
    stmt = (
        select(MemoryRecord)
        .where(MemoryRecord.subject == subject)
        .where(MemoryRecord.valid_from <= timestamp)
        .where((MemoryRecord.valid_until.is_(None)) | (MemoryRecord.valid_until > timestamp))
        .order_by(MemoryRecord.valid_from.desc())
    )
    return (await session.execute(stmt)).scalars().first()


async def history(session: AsyncSession, subject: str) -> list[MemoryRecord]:
    """Every record ever recorded for `subject`, oldest first. Nothing is deleted."""
    stmt = (
        select(MemoryRecord)
        .where(MemoryRecord.subject == subject)
        .order_by(MemoryRecord.valid_from.asc())
    )
    return list((await session.execute(stmt)).scalars().all())
