"""Context Compiler (master §411-450).

Pipeline: DISCOVER -> FILTER -> RANK -> DEDUPLICATE -> VALIDATE ->
RESOLVE TEMPORAL CONFLICTS -> EXPAND REQUIRED DEPENDENCIES -> COMPRESS ->
ESTIMATE TOKENS -> OPTIMIZE -> ASSEMBLE.

Only memory is a real context source today. Skills, tools, code, and
documents are Phase 4-6/13 subsystems that don't exist yet — their pipeline
stages are explicit no-ops (commented where they'd hook in), not silently
skipped, so the shape already matches the target.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.context.models import ContextBundle, ContextItem, ContextSource
from acr.core.tokens import estimate_tokens
from acr.memory.models import MemoryScope
from acr.memory.retrieval import RetrievedMemory, retrieve

# Deterministic compression cap: content beyond this is truncated with a
# marker rather than summarized (no LLM in this stage — see master §15/§421).
_MAX_ITEM_CHARS = 2000


def _memory_to_item(retrieved: RetrievedMemory) -> ContextItem:
    record = retrieved.record
    content = record.content
    compressed = len(content) > _MAX_ITEM_CHARS
    if compressed:
        content = content[:_MAX_ITEM_CHARS] + " ... [truncated]"

    reason = retrieved.selection_reason
    if compressed:
        reason += " [compressed]"

    return ContextItem(
        id=record.id,
        source=ContextSource.MEMORY,
        scope=record.scope.value,
        type=record.type.value,
        content=content,
        token_cost=estimate_tokens(content),
        relevance=retrieved.relevance,
        confidence=record.confidence,
        utility=record.utility_score,
        freshness=max(0.0, 1.0 - record.freshness_days / 30),
        required=False,
        selection_reason=reason,
    )


def _deduplicate(items: list[ContextItem]) -> list[ContextItem]:
    seen: set[str] = set()
    deduped: list[ContextItem] = []
    for item in items:
        key = item.content.strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _validate(items: list[ContextItem]) -> list[ContextItem]:
    return [item for item in items if item.token_cost > 0 and item.content.strip()]


def _optimize(items: list[ContextItem], token_budget: int) -> list[ContextItem]:
    """Greedy knapsack by relevance-per-token; `required` items are always kept."""
    required = [item for item in items if item.required]
    optional = sorted(
        (item for item in items if not item.required),
        key=lambda item: item.relevance / max(item.token_cost, 1),
        reverse=True,
    )
    spent = sum(item.token_cost for item in required)
    selected = list(required)
    for item in optional:
        if spent + item.token_cost > token_budget:
            continue
        selected.append(item)
        spent += item.token_cost
    return selected


async def compile_context(
    session: AsyncSession,
    *,
    task_objective: str,
    scope: MemoryScope | None = None,
    token_budget: int = 4000,
    system_rules: list[str] | None = None,
) -> ContextBundle:
    """Compile a `ContextBundle` for `task_objective` within `token_budget`."""
    # DISCOVER: pull more memory candidates than we expect to keep.
    retrieved = await retrieve(
        session, query=task_objective, scope=scope, token_budget=token_budget * 4
    )

    # FILTER + RANK: acr.memory.retrieval already scoped/filtered/ranked these.
    items = [_memory_to_item(r) for r in retrieved]

    # DEDUPLICATE
    items = _deduplicate(items)

    # VALIDATE
    items = _validate(items)

    # RESOLVE TEMPORAL CONFLICTS: retrieval already restricts to `is_current`
    # records, so no same-subject conflict can reach this stage.

    # EXPAND REQUIRED DEPENDENCIES: no dependency graph exists yet (code
    # indexing is master §1452-1470, a later phase) — no items are marked
    # `required` today, so this stage has nothing to expand.

    # COMPRESS: applied per item in `_memory_to_item` (deterministic truncation).

    # ESTIMATE TOKENS: set per item via acr.core.tokens.estimate_tokens.

    # OPTIMIZE: fit the combined set into the token budget.
    items = _optimize(items, token_budget)

    # ASSEMBLE
    return ContextBundle(
        task_objective=task_objective,
        system_rules=system_rules or [],
        constraints={"token_budget": token_budget},
        items=items,
    )
