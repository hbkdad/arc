"""Tool registry schema (master §826-845).

Tools are code-defined, not user-submitted data the way memories or skills
are — the master spec has no "generate a new tool at runtime" concept
(unlike skills, §19 Skill Generation). A `ToolSpec` is an in-memory
dataclass registered at process startup, not a DB row.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SideEffectLevel(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE_WRITE = "reversible_write"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """The exact required field set from master §827-838."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]
    permissions: list[str] = field(default_factory=list)
    side_effect_level: SideEffectLevel = SideEffectLevel.READ_ONLY
    cost_estimate: float = 0.0
    latency_estimate_ms: int = 0
    network_access: bool = False
    filesystem_access: bool = False
    credential_requirements: list[str] = field(default_factory=list)
