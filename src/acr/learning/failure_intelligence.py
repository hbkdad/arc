"""Failure intelligence (master §615-629): surface similar past failures
before or during planning, so ACR doesn't repeat a mistake it already made
and recorded.

Read-only over `acr.memory.retrieve()` filtered to `MemoryType.FAILURE` --
no new storage, no new ranking heuristic, just a task_class/objective-shaped
entry point over memory that already exists. Never surfaces a raw
free-form `FAILURE` memory as if it had structured fields: a record whose
`structured_payload` doesn't parse as `FailurePayload` (pre-schema, or a
future memory type sharing the FAILURE type) is simply excluded, not
treated as an error.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory.models import MemoryType
from acr.memory.retrieval import retrieve
from acr.memory.schemas import parse_failure_payload

__all__ = ["SimilarFailure", "find_similar_failures"]


@dataclass(frozen=True, slots=True)
class SimilarFailure:
    memory_id: str
    task_class: str
    symptom: str
    root_cause: str | None
    resolution: str | None
    relevance: float


async def find_similar_failures(
    session: AsyncSession,
    *,
    objective: str,
    task_class: str | None = None,
    limit: int = 5,
) -> list[SimilarFailure]:
    """Past `FAILURE` memories whose symptom/content resembles `objective`,
    optionally narrowed to `task_class`. Doesn't count as a memory "use"
    (`record_access=False`) -- looking a failure up isn't the same evidence
    as a skill/memory actually being selected into a task's context."""
    retrieved = await retrieve(
        session,
        query=objective,
        memory_type=MemoryType.FAILURE,
        candidate_pool_size=max(limit * 4, 20),
        record_access=False,
    )

    results: list[SimilarFailure] = []
    for item in retrieved:
        payload = parse_failure_payload(item.record.structured_payload)
        if payload is None:
            continue
        if task_class is not None and payload.task_class != task_class:
            continue
        results.append(
            SimilarFailure(
                memory_id=item.record.id,
                task_class=payload.task_class,
                symptom=payload.symptom,
                root_cause=payload.root_cause,
                resolution=payload.resolution,
                relevance=item.relevance,
            )
        )
        if len(results) >= limit:
            break

    return results
