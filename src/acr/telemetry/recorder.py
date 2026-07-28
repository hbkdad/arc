"""Telemetry event recording.

Every event is persisted (queryable history) and emitted through the
structured logger (real-time visibility) in the same call. Payloads pass
through `acr.security.secrets.redact_mapping` first — master §1024/§1191:
never log secrets or sensitive raw content unnecessarily.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from acr.logging import get_logger
from acr.security.secrets import redact_mapping
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
        safe_payload = redact_mapping(payload or {})
        event = TelemetryEvent(event_type=event_type, task_id=task_id, payload=safe_payload)
        session.add(event)
        await session.flush()
        _logger.info(
            "telemetry.event", event_type=event_type, task_id=task_id, payload=safe_payload
        )
        return event
