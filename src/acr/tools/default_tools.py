"""Built-in tools wrapping existing ACR subsystems.

Real, working tools rather than stubs, so the registry demonstrates actual
end-to-end exposure and invocation, not just metadata bookkeeping.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory.retrieval import retrieve
from acr.skills.search import search as skill_search
from acr.tools.github_search import GITHUB_SEARCH
from acr.tools.models import SideEffectLevel, ToolSpec
from acr.tools.registry import ToolRegistry
from acr.tools.web_fetch import WEB_FETCH


async def _memory_search_handler(
    session: AsyncSession, query: str, limit: int = 5
) -> list[dict[str, Any]]:
    results = await retrieve(session, query=query, candidate_pool_size=limit)
    return [
        {"id": r.record.id, "content": r.record.content, "relevance": r.relevance}
        for r in results[:limit]
    ]


async def _skill_search_handler(
    session: AsyncSession, query: str, limit: int = 5
) -> list[dict[str, Any]]:
    results = await skill_search(session, query, limit=limit)
    return [
        {"id": r.record.id, "description": r.record.description, "rank": r.rank} for r in results
    ]


MEMORY_SEARCH = ToolSpec(
    name="memory_search",
    description="Keyword search over ACR's memory store.",
    input_schema={"query": "string", "limit": "integer"},
    output_schema={"results": "array"},
    handler=_memory_search_handler,
    permissions=["memory.read"],
    side_effect_level=SideEffectLevel.READ_ONLY,
    network_access=False,
    filesystem_access=False,
)

SKILL_SEARCH = ToolSpec(
    name="skill_search",
    description="Keyword search over ACR's skill registry.",
    input_schema={"query": "string", "limit": "integer"},
    output_schema={"results": "array"},
    handler=_skill_search_handler,
    permissions=["skill.read"],
    side_effect_level=SideEffectLevel.READ_ONLY,
    network_access=False,
    filesystem_access=False,
)


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(MEMORY_SEARCH)
    registry.register(SKILL_SEARCH)
    registry.register(WEB_FETCH)
    registry.register(GITHUB_SEARCH)
    return registry
