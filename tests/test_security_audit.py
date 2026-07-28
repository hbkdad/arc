"""Tests for acr.security.audit."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.security.audit import recent_audit_events, record_audit_event
from acr.telemetry.recorder import TelemetryRecorder


async def test_record_audit_event_is_queryable(db_session: AsyncSession) -> None:
    telemetry = TelemetryRecorder()
    await record_audit_event(
        db_session, telemetry, action="tool.invoke:memory_search", outcome="granted"
    )
    await db_session.commit()

    events = await recent_audit_events(db_session)

    assert len(events) == 1
    assert events[0].payload["action"] == "tool.invoke:memory_search"
    assert events[0].payload["outcome"] == "granted"


async def test_record_audit_event_redacts_secrets_in_detail(db_session: AsyncSession) -> None:
    telemetry = TelemetryRecorder()
    await record_audit_event(
        db_session,
        telemetry,
        action="tool.invoke:x",
        outcome="denied",
        detail={"reason": "leaked sk-abcdefghijklmnopqrstuvwxyz012345 in request"},
    )
    await db_session.commit()

    events = await recent_audit_events(db_session)
    assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in events[0].payload["reason"]


async def test_recent_audit_events_respects_limit(db_session: AsyncSession) -> None:
    telemetry = TelemetryRecorder()
    for i in range(5):
        await record_audit_event(db_session, telemetry, action=f"op-{i}", outcome="granted")
    await db_session.commit()

    events = await recent_audit_events(db_session, limit=2)
    assert len(events) == 2
