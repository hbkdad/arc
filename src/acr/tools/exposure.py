"""Dynamic tool exposure (master §843-844).

"Tool exposure must be task-specific. Do not load every tool definition
into every model call." Keyword relevance over each tool's name/description
— deterministic and local, no embeddings — same "start simple" reasoning as
`acr.memory.retrieval` (Phase 2). A task with no *strong* keyword overlap
with any tool gets none, never the full registry by default.

A single shared generic word (e.g. two tools both being "search over X")
isn't enough — `_MIN_RELEVANCE` requires more than one content word's
worth of overlap before a tool counts as relevant. Scoring uses the same
stopword-filtered tokenizer FTS search does (`acr.core.fts_query.tokenize`)
— a bare function word like "a" matching between an unrelated task and a
tool's description is exactly the kind of false-positive overlap that
module already exists to prevent (a real gap this phase's own tests found:
"compile a container image" matched `web_fetch`'s description purely on
the word "a"). Filtering stopwords out of the query shrinks its word
count, which mechanically raises every remaining match's relative score —
`_MIN_RELEVANCE` sits at 1/3 rather than 1/4 to keep a single shared
generic content word (e.g. two tools both named "*_search") from crossing
the threshold on its own (another real gap this phase's tests found).
"""

from __future__ import annotations

from acr.core.fts_query import tokenize
from acr.tools.models import ToolSpec
from acr.tools.registry import ToolRegistry

_MIN_RELEVANCE = 1 / 3


def _score(tool: ToolSpec, query_words: set[str]) -> float:
    tool_words = {w.lower() for w in tokenize(f"{tool.name} {tool.description}")}
    if not query_words or not tool_words:
        return 0.0
    return len(query_words & tool_words) / len(query_words)


def expose_tools(
    registry: ToolRegistry, task_description: str, *, max_tools: int = 5
) -> list[ToolSpec]:
    query_words = {w.lower() for w in tokenize(task_description)}
    scored = [(tool, _score(tool, query_words)) for tool in registry.list_tools()]
    relevant = sorted(
        (pair for pair in scored if pair[1] >= _MIN_RELEVANCE),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [tool for tool, _ in relevant[:max_tools]]
