"""Agent specification (master §747-772).

Agents are temporary workers, not persistent state — an `AgentSpec` is a
plain dataclass, not a DB row (mirrors `acr.tools.models.ToolSpec`'s
reasoning: nothing here is user-submitted data that needs to persist and
evolve the way memories/skills do). What *does* persist is the outcome —
see `acr.agents.topology`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from acr.memory.models import MemoryScope


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """The exact field set from master §749-763."""

    id: str
    role: str
    objective: str
    scope: str
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    memory_scope: MemoryScope = MemoryScope.TASK
    model_policy: dict[str, Any] = field(default_factory=dict)
    token_budget: int = 4000
    money_budget: float = 0.0
    time_budget_seconds: int = 300
    permissions: list[str] = field(default_factory=list)
    communication_policy: str = "none"
    termination_conditions: list[str] = field(default_factory=list)
    verification_requirements: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SpawnEstimate:
    """Master §765-770: estimate before spawning."""

    expected_quality_gain: float
    coordination_overhead: float
    token_cost: int
    latency_benefit: float
    security_risk: float

    @property
    def worth_spawning(self) -> bool:
        """Deterministic v1 heuristic: only worth it if quality gain clears
        coordination overhead plus security risk. Real evidence-based
        estimation needs topology history with enough samples — see
        `acr.agents.topology.recommend_topology`."""
        return self.expected_quality_gain > (self.coordination_overhead + self.security_risk)
