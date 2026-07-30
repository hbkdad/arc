"""MCP server exposure (master §1707-1713, first Phase 13 sub-slice).

Exposes ACR's own capabilities to any MCP client (Claude Code, Claude
Desktop, or anything else speaking the protocol) rather than building a new
integration surface: `memory_search`/`skill_search`/`web_fetch`/
`github_search` are the exact `ToolSpec` handlers Phase 6/13's
`acr.tools.default_tools` already registered, invoked through the same
`acr.tools.invocation.invoke_tool()` permission+audit seam Phase 7 built —
an external MCP client is a *more* untrusted caller than the CLI, not a
less, so it goes through that check rather than around it. `run_task`
mirrors exactly what `acr run` does: routed through the same cheapest-
qualified-and-available ladder (`min_quality_tier=0` by default is always
the zero-config mock provider, no cost, no external calls — identical to
this tool's original hardcoded-mock behavior unless the caller explicitly
raises the tier).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.factory import spawn_agent
from acr.agents.planner import plan_agent
from acr.config import Settings, get_settings
from acr.core.execution import run_task as run_task_engine
from acr.db.base import make_engine, make_session_factory
from acr.routing.models import build_default_router
from acr.security.audit import record_audit_event
from acr.security.permissions import Capability, PermissionDeniedError, PermissionSet
from acr.telemetry.explain import TaskNotFoundError
from acr.telemetry.explain import explain_task as explain_task_impl
from acr.telemetry.recorder import TelemetryRecorder
from acr.telemetry.usage import usage_by_provider
from acr.tools.default_tools import build_default_registry
from acr.tools.invocation import invoke_tool

# Read-only grants matching exactly what memory_search/skill_search/web_fetch/
# github_search declare (master §1131-1149: default deny — an MCP client
# gets nothing beyond what these tools need, no destructive/write capability).
_MCP_GRANTS = PermissionSet(
    frozenset({Capability.MEMORY_READ, Capability.SKILL_READ, Capability.NETWORK_READ})
)


def create_mcp_server(settings: Settings | None = None) -> MCPServer:
    """Build the ACR MCP server against `settings` (or the process default)."""
    settings = settings or get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    registry = build_default_registry()
    router = build_default_router(settings)

    @asynccontextmanager
    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    server = MCPServer(
        name="acr",
        title="ACR — Adaptive Cognitive Runtime",
        description="Local-first memory, skills, and task execution.",
        version="0.1.0",
    )

    @server.tool(description="Keyword search over ACR's local memory store.")
    async def memory_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
        async with _session() as session:
            telemetry = TelemetryRecorder()
            result = await invoke_tool(
                session,
                registry,
                "memory_search",
                grants=_MCP_GRANTS,
                telemetry=telemetry,
                query=query,
                limit=limit,
            )
            await session.commit()
            return result

    @server.tool(description="Keyword search over ACR's local skill registry.")
    async def skill_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
        async with _session() as session:
            telemetry = TelemetryRecorder()
            result = await invoke_tool(
                session,
                registry,
                "skill_search",
                grants=_MCP_GRANTS,
                telemetry=telemetry,
                query=query,
                limit=limit,
            )
            await session.commit()
            return result

    @server.tool(description="Fetch a URL over HTTP(S) and return its extracted text.")
    async def web_fetch(url: str, max_chars: int = 4000) -> dict[str, Any]:
        async with _session() as session:
            telemetry = TelemetryRecorder()
            result = await invoke_tool(
                session,
                registry,
                "web_fetch",
                grants=_MCP_GRANTS,
                telemetry=telemetry,
                url=url,
                max_chars=max_chars,
            )
            await session.commit()
            return result

    @server.tool(description="Search GitHub issues and pull requests (read-only).")
    async def github_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
        async with _session() as session:
            telemetry = TelemetryRecorder()
            result = await invoke_tool(
                session,
                registry,
                "github_search",
                grants=_MCP_GRANTS,
                telemetry=telemetry,
                query=query,
                limit=limit,
            )
            await session.commit()
            return result

    @server.tool(
        description=(
            "Render a URL in a real headless browser and return its visible text, "
            "including JS-rendered content web_fetch can't see."
        )
    )
    async def browser_fetch(url: str, max_chars: int = 4000) -> dict[str, Any]:
        async with _session() as session:
            telemetry = TelemetryRecorder()
            result = await invoke_tool(
                session,
                registry,
                "browser_fetch",
                grants=_MCP_GRANTS,
                telemetry=telemetry,
                url=url,
                max_chars=max_chars,
            )
            await session.commit()
            return result

    @server.tool(
        description=(
            "Run an objective through ACR's task engine. Uses the zero-config mock "
            "provider unless min_quality_tier is raised (or "
            "Settings.default_min_quality_tier is configured) to prefer a "
            "configured Ollama/cloud provider instead. Pass task_class to route "
            "real skills for the objective and feed the outcome back into skill "
            "reliability and topology evidence (see `acr agents topology`) -- the "
            "same evidence loop `acr agents spawn` closes, now reachable from any "
            "MCP client's real usage too, not just CLI-driven dogfooding. Omitting "
            "task_class runs the plain task engine with no routing/recording, "
            "identical to this tool's original behavior."
        )
    )
    async def run_task(
        objective: str,
        min_quality_tier: int | None = None,
        task_class: str | None = None,
    ) -> dict[str, Any]:
        resolved_tier = (
            min_quality_tier if min_quality_tier is not None else settings.default_min_quality_tier
        )
        profile = await router.select(min_quality_tier=resolved_tier)
        async with _session() as session:
            telemetry = TelemetryRecorder()
            # Every other tool in this server goes through invoke_tool()'s
            # permission+audit seam (see module docstring); this one bypassed
            # it entirely -- an MCP client could pass min_quality_tier itself
            # and force a real, billed cloud completion with zero permission
            # check and zero audit trail. Gate on the *resolved* provider's
            # actual cost (not the requested tier, which could drift out of
            # sync with build_default_router()'s tier assignments) and audit
            # every call, granted or denied, the same way invoke_tool() does.
            try:
                if profile.cost_per_1k_tokens > 0:
                    _MCP_GRANTS.require(Capability.CREDENTIAL_USE)
            except PermissionDeniedError as exc:
                await record_audit_event(
                    session,
                    telemetry,
                    action="tool.invoke:run_task",
                    outcome="denied",
                    detail={"reason": str(exc), "provider": profile.name},
                )
                await session.commit()
                raise

            if task_class is not None:
                # force=True: an MCP caller explicitly asking to run an
                # objective isn't opting into agents.factory's separate
                # cost/risk "worth spawning" gate (acr run doesn't have
                # one either) -- mirrors run_task_engine's unconditional
                # execution below, just via the routing-aware path.
                spec = await plan_agent(session, objective, task_class=task_class)
                task, review = await spawn_agent(
                    session, spec, profile.provider, telemetry, task_class=task_class, force=True
                )
                await record_audit_event(
                    session,
                    telemetry,
                    action="tool.invoke:run_task",
                    outcome="granted",
                    detail={
                        "provider": profile.name,
                        "task_class": task_class,
                        "skills": spec.skills,
                    },
                    task_id=task.id,
                )
                await session.commit()
                return {
                    "id": task.id,
                    "objective": task.objective,
                    "status": task.status.value,
                    "skills_routed": spec.skills,
                    "review_passed": review.passed,
                }

            task = await run_task_engine(session, objective, profile.provider, telemetry)
            await record_audit_event(
                session,
                telemetry,
                action="tool.invoke:run_task",
                outcome="granted",
                detail={"provider": profile.name},
                task_id=task.id,
            )
            await session.commit()
            return {"id": task.id, "objective": task.objective, "status": task.status.value}

    # explain_task/usage_summary are plain reads of already-recorded
    # telemetry -- no capability gate, matching `acr explain`/`acr models
    # usage`'s own CLI commands (neither has a permission check either) and
    # the dashboard's own read-only presentation layer. Nothing here can
    # trigger a network call, spend a credential, or mutate any state.
    @server.tool(
        description=(
            "Replay a task's real telemetry trail (provider, tokens, duration) -- "
            "the same data `acr explain <task-id>` prints, for an MCP client "
            "debugging a task without shelling out to the CLI."
        )
    )
    async def explain_task(task_id: str) -> dict[str, Any]:
        async with _session() as session:
            try:
                explanation = await explain_task_impl(session, task_id)
            except TaskNotFoundError:
                return {"error": f"no task with id {task_id!r}"}
            return {
                "id": explanation.task.id,
                "objective": explanation.task.objective,
                "status": explanation.task.status.value,
                "provider": explanation.provider,
                "output_tokens": explanation.output_tokens,
                "duration_seconds": explanation.duration_seconds,
                "events": [
                    {"event_type": e.event_type, "created_at": e.created_at.isoformat()}
                    for e in explanation.events
                ],
            }

    @server.tool(
        description=(
            "Real per-provider call counts, tokens, and estimated cost from every "
            "recorded model.call.completed event -- the same data `/routing` and "
            "`acr models usage` show, for an MCP client checking spend without a "
            "browser."
        )
    )
    async def usage_summary() -> list[dict[str, Any]]:
        async with _session() as session:
            usage = await usage_by_provider(session, router.profiles)
            return [
                {
                    "provider": u.provider,
                    "call_count": u.call_count,
                    "input_tokens": u.input_tokens,
                    "output_tokens": u.output_tokens,
                    "estimated_cost": u.estimated_cost,
                }
                for u in usage
            ]

    return server
