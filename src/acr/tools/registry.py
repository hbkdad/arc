"""In-memory tool registry (master §826-845).

Tool exposure must be task-specific — `acr.tools.exposure.expose_tools`
reads this registry, but a model call is never handed every tool definition
(master §844).
"""

from __future__ import annotations

from acr.tools.models import ToolSpec


class DuplicateToolError(ValueError):
    """Raised when registering a tool name that's already registered."""


class ToolNotFoundError(LookupError):
    """Raised when looking up an unregistered tool name."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise DuplicateToolError(spec.name)
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(name) from None

    def list_tools(self) -> list[ToolSpec]:
        return sorted(self._tools.values(), key=lambda tool: tool.name)
