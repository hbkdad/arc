"""MCP server exposure (master §1707-1713, first Phase 13 sub-slice).

Exposes ACR's own capabilities to any MCP client (Claude Code, Claude
Desktop, or anything else speaking the protocol) rather than building a new
integration surface: `memory_search`/`skill_search` are the exact `ToolSpec`
handlers Phase 6 already registered in `acr.tools.default_tools`, invoked
through the same `acr.tools.invocation.invoke_tool()` permission+audit seam
Phase 7 built — an external MCP client is a *more* untrusted caller than
the CLI, not a less, so it goes through that check rather than around it.
`run_task` mirrors exactly what `acr run` already does (the zero-config
mock provider, no cost, no external calls) — real provider routing for
MCP-triggered tasks is future work, same caveat the CLI's own `run`
command carries today.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy.ext.asyncio import AsyncSession

from acr.config import Settings, get_settings
from acr.core.execution import run_task as run_task_engine
from acr.core.tasks.models import Task
from acr.db.base import make_engine, make_session_factory
from acr.providers.mock import MockProvider
from acr.security.permissions import Capability, PermissionSet
from acr.telemetry.recorder import TelemetryRecorder
from acr.tools.default_tools import build_default_registry
from acr.tools.invocation import invoke_tool

# Read-only grants matching exactly what memory_search/skill_search declare
# (master §1131-1149: default deny — an MCP client gets nothing beyond
# what these two specific tools need, no destructive/write capability).
_MCP_GRANTS = PermissionSet(frozenset({Capability.MEMORY_READ, Capability.SKILL_READ}))


def create_mcp_server(settings: Settings | None = None) -> MCPServer:
    """Build the ACR MCP server against `settings` (or the process default)."""
    settings = settings or get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    registry = build_default_registry()

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

    @server.tool(description="Run an objective through ACR's task engine (mock provider).")
    async def run_task(objective: str) -> dict[str, Any]:
        async with _session() as session:
            task: Task = await run_task_engine(
                session, objective, MockProvider(), TelemetryRecorder()
            )
            return {"id": task.id, "objective": task.objective, "status": task.status.value}

    return server
