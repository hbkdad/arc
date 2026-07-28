"""Audit logging (master §1178-1179, §1237).

Reuses the telemetry system (Phase 1) rather than building a parallel
logging path — a `security.audit` event is a `TelemetryEvent` like any
other, queryable the same way `waste_analyzer` queries `context.attribution`
events.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.telemetry.models import TelemetryEvent
from acr.telemetry.recorder import TelemetryRecorder

AUDIT_EVENT_TYPE = "security.audit"


async def record_audit_event(
    session: AsyncSession,
    telemetry: TelemetryRecorder,
    *,
    action: str,
    outcome: str,
    detail: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> TelemetryEvent:
    """Record a security-relevant event: a permission check, a safe-mode
    block, an injection-scan hit. `outcome` is a short label ("granted",
    "denied", "blocked", "detected") — keep it enumerable, not free text.
    """
    payload = {"action": action, "outcome": outcome, **(detail or {})}
    return await telemetry.emit(session, AUDIT_EVENT_TYPE, task_id=task_id, payload=payload)


async def recent_audit_events(session: AsyncSession, *, limit: int = 50) -> list[TelemetryEvent]:
    stmt = (
        select(TelemetryEvent)
        .where(TelemetryEvent.event_type == AUDIT_EVENT_TYPE)
        .order_by(TelemetryEvent.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
