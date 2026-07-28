"""Context items and the compiled ContextBundle (master §411-450).

Every context item carries the exact field set master §425-436 requires:
id, source, scope, type, token_cost, relevance, confidence, utility,
freshness, required, selection_reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ContextSource(StrEnum):
    MEMORY = "memory"
    SKILL = "skill"
    TOOL = "tool"
    CODE = "code"
    DOCUMENT = "document"
    OBSERVATION = "observation"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class ContextItem:
    id: str
    source: ContextSource
    scope: str
    type: str
    content: str
    token_cost: int
    relevance: float
    confidence: float
    utility: float
    freshness: float
    required: bool
    selection_reason: str


@dataclass(slots=True)
class ContextBundle:
    """master §437-450: system rules, objective, constraints, selected
    context, and the output/verification contracts the model must follow.

    `selected_skills`/`selected_tools`/`selected_code`/`selected_documents`/
    `previous_observations` are always empty today — those subsystems don't
    exist yet (Phases 4-6, 13). They're explicit fields, not omitted, so the
    bundle's shape already matches the target and each fills in exactly once
    its subsystem lands.
    """

    task_objective: str
    system_rules: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    items: list[ContextItem] = field(default_factory=list)
    output_contract: dict[str, Any] = field(default_factory=dict)
    verification_contract: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return sum(item.token_cost for item in self.items)

    def items_by_source(self, source: ContextSource) -> list[ContextItem]:
        return [item for item in self.items if item.source is source]
