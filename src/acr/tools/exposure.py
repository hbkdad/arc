"""Dynamic tool exposure (master §843-844).

"Tool exposure must be task-specific. Do not load every tool definition
into every model call." Keyword relevance over each tool's name/description
— deterministic and local, no embeddings — same "start simple" reasoning as
`acr.memory.retrieval` (Phase 2). A task with no *strong* keyword overlap
with any tool gets none, never the full registry by default.

A single shared generic word (e.g. two tools both being "search over X")
isn't enough — `_MIN_RELEVANCE` requires a meaningful fraction of the task
description's words to match before a tool counts as relevant, otherwise
every tool in a registry full of "search" tools would match every query
that happens to mention searching.
"""

from __future__ import annotations

import re

from acr.tools.models import ToolSpec
from acr.tools.registry import ToolRegistry

_WORD_PATTERN = re.compile(r"[A-Za-z0-9_]+")
_MIN_RELEVANCE = 0.25


def _score(tool: ToolSpec, query_words: set[str]) -> float:
    tool_words = set(_WORD_PATTERN.findall(f"{tool.name} {tool.description}".lower()))
    if not query_words or not tool_words:
        return 0.0
    return len(query_words & tool_words) / len(query_words)


def expose_tools(
    registry: ToolRegistry, task_description: str, *, max_tools: int = 5
) -> list[ToolSpec]:
    query_words = set(_WORD_PATTERN.findall(task_description.lower()))
    scored = [(tool, _score(tool, query_words)) for tool in registry.list_tools()]
    relevant = sorted(
        (pair for pair in scored if pair[1] >= _MIN_RELEVANCE),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [tool for tool, _ in relevant[:max_tools]]
