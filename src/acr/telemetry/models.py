"""Telemetry event storage (master §992-1024).

Payloads are structured JSON. Callers are responsible for never putting
secrets in `payload` — see master §1024 and §41.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from acr.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)
    event_type: Mapped[str] = mapped_column(index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
