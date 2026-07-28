"""Tool registry and dynamic exposure (master §826-845)."""

from acr.tools.default_tools import MEMORY_SEARCH, SKILL_SEARCH, build_default_registry
from acr.tools.exposure import expose_tools
from acr.tools.invocation import invoke_tool
from acr.tools.models import SideEffectLevel, ToolSpec
from acr.tools.registry import DuplicateToolError, ToolNotFoundError, ToolRegistry

__all__ = [
    "MEMORY_SEARCH",
    "SKILL_SEARCH",
    "DuplicateToolError",
    "SideEffectLevel",
    "ToolNotFoundError",
    "ToolRegistry",
    "ToolSpec",
    "build_default_registry",
    "expose_tools",
    "invoke_tool",
]
