"""Hybrid memory retrieval (master §530-551).

Pipeline: retrieve more candidates than will be selected -> filter by scope/
type/status/temporal validity -> rank (keyword relevance + confidence +
importance + historical utility) -> select within a token budget -> return
selection explanations.

Semantic (embedding) similarity is intentionally not implemented yet: the
Phase 2 milestone (master §1644-1649) calls out "FTS retrieval", not
semantic retrieval, and adding an embeddings model now would be
infrastructure ahead of evidence it's needed (master principle #23).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.fts_query import bm25_to_relevance, build_match_query
from acr.core.tokens import estimate_tokens
from acr.memory.models import MemoryRecord, MemoryScope, MemoryStatus, MemoryType, utcnow

__all__ = ["RetrievedMemory", "estimate_tokens", "retrieve"]

_ACTIVE_STATUSES = (MemoryStatus.CANDIDATE, MemoryStatus.CONFIRMED)


@dataclass(frozen=True, slots=True)
class RetrievedMemory:
    record: MemoryRecord
    relevance: float
    token_cost: int
    selection_reason: str


async def _fts_ranks(session: AsyncSession, query: str, limit: int) -> dict[str, float]:
    """Full-text search via SQLite FTS5. Returns {memory_id: bm25_rank} (lower = more relevant)."""
    match_query = build_match_query(query)
    if not match_query:
        return {}
    rows = (
        await session.execute(
            text(
                """
                SELECT memory_records.id AS id, bm25(memory_fts) AS rank
                FROM memory_fts
                JOIN memory_records ON memory_records.rowid = memory_fts.rowid
                WHERE memory_fts MATCH :query
                ORDER BY rank
                LIMIT :limit
                """
            ),
            {"query": match_query, "limit": limit},
        )
    ).all()
    return {row.id: row.rank for row in rows}


async def retrieve(
    session: AsyncSession,
    *,
    query: str = "",
    scope: MemoryScope | None = None,
    memory_type: MemoryType | None = None,
    token_budget: int = 2000,
    candidate_pool_size: int = 50,
    record_access: bool = True,
) -> list[RetrievedMemory]:
    """Retrieve a token-budgeted, ranked, explained set of memories.

    If `query` is blank, ranking falls back to confidence/importance/utility
    only (keyword search contributes nothing, matching "no query" rather than
    "no results").
    """
    fts_ranks = await _fts_ranks(session, query, candidate_pool_size)

    stmt = select(MemoryRecord).where(MemoryRecord.status.in_(_ACTIVE_STATUSES))
    if scope is not None:
        stmt = stmt.where(MemoryRecord.scope == scope)
    if memory_type is not None:
        stmt = stmt.where(MemoryRecord.type == memory_type)
    if query.strip():
        if not fts_ranks:
            return []
        stmt = stmt.where(MemoryRecord.id.in_(fts_ranks))
    stmt = stmt.limit(candidate_pool_size)

    records = (await session.execute(stmt)).scalars().all()

    now = utcnow()
    scored: list[RetrievedMemory] = []
    for record in records:
        if not record.is_current:
            continue

        keyword_score = bm25_to_relevance(fts_ranks[record.id]) if record.id in fts_ranks else 0.0
        utility = record.successful_uses / record.access_count if record.access_count > 0 else 0.5
        relevance = (
            keyword_score * 0.5 + record.confidence * 0.2 + record.importance * 0.2 + utility * 0.1
        )
        scored.append(
            RetrievedMemory(
                record=record,
                relevance=relevance,
                token_cost=estimate_tokens(record.content),
                selection_reason=(
                    f"keyword={keyword_score:.2f} confidence={record.confidence:.2f} "
                    f"importance={record.importance:.2f} utility={utility:.2f}"
                ),
            )
        )

    scored.sort(key=lambda item: item.relevance, reverse=True)

    selected: list[RetrievedMemory] = []
    spent = 0
    for item in scored:
        if spent + item.token_cost > token_budget:
            continue
        selected.append(item)
        spent += item.token_cost

    if record_access:
        for item in selected:
            item.record.access_count += 1
            item.record.last_accessed = now

    return selected
