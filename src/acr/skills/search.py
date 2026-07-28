"""Skill search over the registry (master §683: discoverable without loading
every skill into context — this queries `skills`/`skills_fts` metadata only,
never reads a skill package's files off disk)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.fts_query import build_match_query
from acr.skills.models import SkillRecord, SkillStatus


@dataclass(frozen=True, slots=True)
class SkillSearchResult:
    record: SkillRecord
    rank: float


async def search(
    session: AsyncSession,
    query: str,
    *,
    status: SkillStatus | None = None,
    limit: int = 20,
) -> list[SkillSearchResult]:
    """Keyword search over skill name/description via SQLite FTS5."""
    match_query = build_match_query(query)
    if not match_query:
        return []

    rows = (
        await session.execute(
            text(
                """
                SELECT skills.id AS id, bm25(skills_fts) AS rank
                FROM skills_fts
                JOIN skills ON skills.rowid = skills_fts.rowid
                WHERE skills_fts MATCH :query
                ORDER BY rank
                LIMIT :limit
                """
            ),
            {"query": match_query, "limit": limit},
        )
    ).all()
    if not rows:
        return []

    ranks = {row.id: row.rank for row in rows}
    stmt = select(SkillRecord).where(SkillRecord.id.in_(ranks))
    if status is not None:
        stmt = stmt.where(SkillRecord.status == status)
    records = (await session.execute(stmt)).scalars().all()

    results = [SkillSearchResult(record=r, rank=ranks[r.id]) for r in records]
    results.sort(key=lambda item: item.rank)
    return results
