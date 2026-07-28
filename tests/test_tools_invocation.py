"""Tests for acr.tools.invocation (master §826-845 + §1131-1149 + §1534-1550)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory import MemoryCandidate, MemoryScope, MemoryType
from acr.memory.write_controller import remember
from acr.security.audit import recent_audit_events
from acr.security.permissions import Capability, PermissionDeniedError, PermissionSet
from acr.security.safe_mode import SafeModeError
from acr.telemetry.recorder import TelemetryRecorder
from acr.tools.default_tools import build_default_registry
from acr.tools.invocation import invoke_tool
from acr.tools.models import SideEffectLevel, ToolSpec
from acr.tools.registry import ToolRegistry


async def test_invoke_tool_succeeds_with_granted_permissions(db_session: AsyncSession) -> None:
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
    registry = build_default_registry()
    grants = PermissionSet(granted=frozenset({Capability.MEMORY_READ}))

    results = await invoke_tool(
        db_session,
        registry,
        "memory_search",
        grants=grants,
        telemetry=TelemetryRecorder(),
        query="SQLite",
    )

    assert len(results) == 1


async def test_invoke_tool_denies_without_permission(db_session: AsyncSession) -> None:
    registry = build_default_registry()
    grants = PermissionSet()  # nothing granted

    with pytest.raises(PermissionDeniedError):
        await invoke_tool(
            db_session,
            registry,
            "memory_search",
            grants=grants,
            telemetry=TelemetryRecorder(),
            query="SQLite",
        )

    await db_session.commit()
    events = await recent_audit_events(db_session)
    assert events[0].payload["outcome"] == "denied"


async def test_invoke_tool_read_only_ignores_safe_mode(db_session: AsyncSession) -> None:
    registry = build_default_registry()
    grants = PermissionSet(granted=frozenset({Capability.MEMORY_READ}))

    # memory_search is READ_ONLY, so safe mode must not block it.
    results = await invoke_tool(
        db_session,
        registry,
        "memory_search",
        grants=grants,
        telemetry=TelemetryRecorder(),
        safe_mode=True,
        query="anything",
    )
    assert results == []


async def test_invoke_tool_blocks_reversible_write_in_safe_mode(db_session: AsyncSession) -> None:
    async def _handler(session: AsyncSession) -> str:
        return "did a write"

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="fake_writer",
            description="pretend write tool",
            input_schema={},
            output_schema={},
            handler=_handler,
            permissions=[],
            side_effect_level=SideEffectLevel.REVERSIBLE_WRITE,
        )
    )
    grants = PermissionSet()

    with pytest.raises(SafeModeError):
        await invoke_tool(
            db_session,
            registry,
            "fake_writer",
            grants=grants,
            telemetry=TelemetryRecorder(),
            safe_mode=True,
        )
