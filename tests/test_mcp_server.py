"""Tests for acr.integrations.mcp_server (master §1707-1713)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mcp.types import CallToolResult
from sqlalchemy.ext.asyncio import AsyncSession

from acr.config import Settings
from acr.integrations.mcp_server import create_mcp_server
from acr.memory import MemoryCandidate, MemoryScope, MemoryType
from acr.memory.write_controller import remember
from acr.security.audit import recent_audit_events
from acr.skills.models import SkillStatus
from acr.skills.registry import register, set_status

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


def _structured(result: object) -> dict[str, Any]:
    """Narrow call_tool()'s CallToolResult | InputRequiredResult union.

    None of these tools elicit input, so a real InputRequiredResult would
    itself be a test failure worth seeing, not something to silently handle.
    """
    assert isinstance(result, CallToolResult)
    assert result.is_error is not True
    assert result.structured_content is not None
    return result.structured_content


async def test_memory_search_tool_finds_a_real_seeded_record(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await remember(
        db_session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject="acr.mcp",
            content="MCP exposes ACR's memory search to external clients",
            source_type="session",
            confidence=0.9,
            evidence="observed directly",
        ),
    )
    await db_session.commit()

    server = create_mcp_server(migrated_settings)
    result = await server.call_tool("memory_search", {"query": "MCP exposes", "limit": 5})

    hits = _structured(result)["result"]
    assert any("MCP exposes" in h["content"] for h in hits)


async def test_memory_search_tool_returns_empty_for_no_match(migrated_settings: Settings) -> None:
    server = create_mcp_server(migrated_settings)
    result = await server.call_tool("memory_search", {"query": "nothing seeded", "limit": 5})

    assert _structured(result)["result"] == []


async def test_skill_search_tool_finds_a_registered_skill(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await register(db_session, FIXTURES / "sqlite-diagnostics")
    await set_status(db_session, "sqlite-diagnostics", SkillStatus.ACTIVE)
    await db_session.commit()

    server = create_mcp_server(migrated_settings)
    result = await server.call_tool("skill_search", {"query": "sqlite", "limit": 5})

    hits = _structured(result)["result"]
    assert any(h["id"] == "sqlite-diagnostics" for h in hits)


async def test_run_task_tool_executes_a_real_task(migrated_settings: Settings) -> None:
    server = create_mcp_server(migrated_settings)
    result = await server.call_tool("run_task", {"objective": "say hello via mcp"})

    body = _structured(result)
    assert body["objective"] == "say hello via mcp"
    assert body["status"] == "completed"


async def test_run_task_tool_reports_no_provider_available(migrated_settings: Settings) -> None:
    from mcp.server.mcpserver.exceptions import ToolError

    server = create_mcp_server(migrated_settings)
    with pytest.raises(ToolError, match="min_quality_tier"):
        await server.call_tool(
            "run_task", {"objective": "say hello via mcp", "min_quality_tier": 5}
        )


async def test_run_task_tool_denies_a_credentialed_provider(migrated_settings: Settings) -> None:
    # An MCP client is a more untrusted caller than the local CLI (see the
    # module docstring) -- it must not be able to force a real, billed
    # cloud completion just by passing min_quality_tier=2 itself. Ollama is
    # tier 1, so it's excluded from tier-2 candidates regardless of whether
    # a real daemon happens to be reachable on the machine running this
    # test -- only the credentialed cloud providers qualify, keeping this
    # deterministic.
    from mcp.server.mcpserver.exceptions import ToolError

    settings = migrated_settings.model_copy(update={"openai_api_key": "sk-fake"})
    server = create_mcp_server(settings)

    with pytest.raises(ToolError, match=r"credential\.use"):
        await server.call_tool(
            "run_task", {"objective": "say hello via mcp", "min_quality_tier": 2}
        )


async def test_run_task_tool_denial_is_audited(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    from mcp.server.mcpserver.exceptions import ToolError

    settings = migrated_settings.model_copy(update={"openai_api_key": "sk-fake"})
    server = create_mcp_server(settings)

    with pytest.raises(ToolError):
        await server.call_tool(
            "run_task", {"objective": "say hello via mcp", "min_quality_tier": 2}
        )

    events = await recent_audit_events(db_session)
    assert any(
        e.payload.get("action") == "tool.invoke:run_task" and e.payload.get("outcome") == "denied"
        for e in events
    )


async def test_run_task_tool_success_is_audited(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    server = create_mcp_server(migrated_settings)
    await server.call_tool("run_task", {"objective": "say hello via mcp"})

    events = await recent_audit_events(db_session)
    assert any(
        e.payload.get("action") == "tool.invoke:run_task" and e.payload.get("outcome") == "granted"
        for e in events
    )


async def test_run_task_tool_honors_settings_default_min_quality_tier(
    migrated_settings: Settings,
) -> None:
    from mcp.server.mcpserver.exceptions import ToolError

    # Settings.default_min_quality_tier is the persistent opt-in: with no
    # provider satisfying tier 5, an MCP caller that omits min_quality_tier
    # entirely must still fail the same way an explicit tier=5 would --
    # proving the settings value reaches router.select(), not just the
    # tool's own hardcoded None-means-mock fallback.
    settings = migrated_settings.model_copy(update={"default_min_quality_tier": 5})
    server = create_mcp_server(settings)
    with pytest.raises(ToolError, match="min_quality_tier"):
        await server.call_tool("run_task", {"objective": "say hello via mcp"})


async def test_web_fetch_tool_fetches_real_content(
    migrated_settings: Settings, local_html_server: str
) -> None:
    server = create_mcp_server(migrated_settings)
    result = await server.call_tool("web_fetch", {"url": local_html_server + "/"})

    body = _structured(result)
    assert "Hello" in body["text"]
    assert body["status_code"] == 200


async def test_github_search_tool_returns_parsed_results(
    migrated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from acr.tools import github_search as github_search_module

    async def _fake_run_gh_api(endpoint: str) -> dict[str, Any]:
        return {
            "items": [
                {
                    "repository_url": "https://api.github.com/repos/hbkdad/arc",
                    "number": 1,
                    "title": "example",
                    "state": "open",
                    "html_url": "https://github.com/hbkdad/arc/issues/1",
                    "comments": 0,
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        }

    monkeypatch.setattr(github_search_module, "_run_gh_api", _fake_run_gh_api)

    server = create_mcp_server(migrated_settings)
    result = await server.call_tool("github_search", {"query": "repo:hbkdad/arc", "limit": 5})

    hits = _structured(result)["result"]
    assert hits[0]["repository"] == "hbkdad/arc"


async def test_memory_search_tool_is_audited(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    from acr.security.audit import recent_audit_events

    server = create_mcp_server(migrated_settings)
    await server.call_tool("memory_search", {"query": "anything", "limit": 5})

    events = await recent_audit_events(db_session)
    assert any(e.payload.get("action") == "tool.invoke:memory_search" for e in events)
