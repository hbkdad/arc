"""Agent planning (master §747-763: what an `AgentSpec` is scoped to).

The smallest complete planner: one agent per objective (master principle
#24 / §771-772 — "use the minimum number of agents required... do not
create agents for visual spectacle"), scoped to real, currently-routable
skills and tools via the routers Phases 4 and 6 already built — not a
placeholder empty spec.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.models import AgentSpec
from acr.memory.models import MemoryScope
from acr.skills.routing import route
from acr.tools.default_tools import build_default_registry
from acr.tools.exposure import expose_tools


async def plan_agent(
    session: AsyncSession,
    objective: str,
    *,
    role: str = "worker",
    token_budget: int = 4000,
    task_class: str | None = None,
) -> AgentSpec:
    """Build a single-agent plan for `objective`, granting only the skills
    and tools the existing routers judge relevant — never the full registry
    (the same task-specific-exposure principle Phase 6 established).

    `task_class`, when the caller has one (e.g. `agents spawn --task-class`),
    is passed straight through to `route()` so an exact task_class match can
    surface a skill even with zero keyword overlap against `objective` —
    otherwise routing depends on keyword relevance alone."""
    routed_skills = await route(session, objective, task_class=task_class)
    exposed_tools = expose_tools(build_default_registry(), objective)

    return AgentSpec(
        id=f"agent-{uuid.uuid4().hex[:8]}",
        role=role,
        objective=objective,
        scope="task",
        tools=[tool.name for tool in exposed_tools],
        skills=[routed.record.id for routed in routed_skills],
        memory_scope=MemoryScope.TASK,
        token_budget=token_budget,
    )
