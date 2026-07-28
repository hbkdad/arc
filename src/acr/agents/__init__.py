"""Agents: specification, factory, planner, critic, topology history
(master §747-793)."""

from acr.agents.critic import review_agent_task
from acr.agents.factory import estimate_spawn, spawn_agent
from acr.agents.models import AgentSpec, SpawnEstimate
from acr.agents.planner import plan_agent
from acr.agents.topology import (
    AgentTopologyRecord,
    TopologyRecommendation,
    recommend_topology,
    record_topology,
)

__all__ = [
    "AgentSpec",
    "AgentTopologyRecord",
    "SpawnEstimate",
    "TopologyRecommendation",
    "estimate_spawn",
    "plan_agent",
    "recommend_topology",
    "record_topology",
    "review_agent_task",
    "spawn_agent",
]
