"""Telemetry event recording.

Every event is persisted (queryable history) and emitted through the
structured logger (real-time visibility) in the same call.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from acr.logging import get_logger
from acr.telemetry.models import TelemetryEvent

_logger = get_logger("acr.telemetry")


class TelemetryRecorder:
    """Records telemetry events to the database and the structured logger."""

    async def emit(
        self,
        session: AsyncSession,
        event_type: str,
        *,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> TelemetryEvent:
        event = TelemetryEvent(event_type=event_type, task_id=task_id, payload=payload or {})
        session.add(event)
        await session.flush()
        _logger.info(
            "telemetry.event", event_type=event_type, task_id=task_id, payload=payload or {}
        )
        return event
