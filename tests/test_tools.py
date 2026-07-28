"""Tests for acr.tools (master §826-845)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory import MemoryCandidate, MemoryScope, MemoryType
from acr.memory.write_controller import remember
from acr.tools.default_tools import MEMORY_SEARCH, build_default_registry
from acr.tools.exposure import expose_tools
from acr.tools.models import SideEffectLevel
from acr.tools.registry import DuplicateToolError, ToolNotFoundError, ToolRegistry


def test_registry_registers_and_gets_a_tool() -> None:
    registry = ToolRegistry()
    registry.register(MEMORY_SEARCH)

    assert registry.get("memory_search") is MEMORY_SEARCH


def test_registry_rejects_duplicate_names() -> None:
    registry = ToolRegistry()
    registry.register(MEMORY_SEARCH)

    with pytest.raises(DuplicateToolError):
        registry.register(MEMORY_SEARCH)


def test_registry_raises_for_unknown_tool() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.get("does-not-exist")


def test_default_registry_has_memory_skill_web_github_and_browser_search() -> None:
    registry = build_default_registry()
    names = {tool.name for tool in registry.list_tools()}
    assert names == {
        "memory_search",
        "skill_search",
        "web_fetch",
        "github_search",
        "browser_fetch",
    }
    assert all(
        tool.side_effect_level is SideEffectLevel.READ_ONLY for tool in registry.list_tools()
    )


def test_expose_tools_returns_only_relevant_tools() -> None:
    registry = build_default_registry()

    exposed = expose_tools(registry, "search the memory store for a fact")

    assert exposed == [MEMORY_SEARCH]


def test_expose_tools_returns_nothing_for_unrelated_task() -> None:
    registry = build_default_registry()

    exposed = expose_tools(registry, "compile a container image")

    assert exposed == []


def test_expose_tools_respects_max_tools() -> None:
    registry = build_default_registry()

    exposed = expose_tools(registry, "search memory and skills", max_tools=1)

    assert len(exposed) == 1


async def test_memory_search_tool_handler_finds_real_memories(db_session: AsyncSession) -> None:
    await remember(
        db_session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject="acr.db",
            content="ACR persists data in a local SQLite file.",
            source_type="session",
            confidence=0.9,
            evidence="test fixture",
        ),
    )

    results = await MEMORY_SEARCH.handler(db_session, "SQLite")

    assert len(results) == 1
    assert "SQLite" in results[0]["content"]
