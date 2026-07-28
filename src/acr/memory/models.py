"""Memory schema (master spec §473-529).

Memory is one unified, typed table rather than one table per `MemoryType` —
the master spec's own hybrid-retrieval requirement (§530-551) operates
uniformly across types (keyword, metadata, temporal, scope), which a single
schema with a `type` discriminator serves directly. Failure memory (§615-629)
is `MemoryType.FAILURE` with its task-class/symptom/root-cause/resolution
fields carried in `structured_payload` rather than a bespoke table.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from acr.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime) -> datetime:
    """SQLite has no timezone-aware datetime type: a value written as UTC
    comes back from a real round-trip through the database as naive. Treat a
    naive value as UTC (everything this module writes is UTC) rather than
    letting `datetime` subtraction/comparison raise."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MemoryType(StrEnum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    FAILURE = "failure"
    DECISION = "decision"
    PREFERENCE = "preference"
    ENVIRONMENT = "environment"
    SECURITY = "security"
    TEMPORARY = "temporary"


class MemoryScope(StrEnum):
    GLOBAL = "global"
    ORGANIZATION = "organization"
    USER = "user"
    PROJECT = "project"
    REPOSITORY = "repository"
    TASK = "task"
    AGENT = "agent"
    SESSION = "session"


class MemoryStatus(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    QUARANTINED = "quarantined"
    DELETED = "deleted"


class MemoryRecord(Base):
    """A single memory record (master §485-518).

    `freshness` is deliberately not a stored column — it is inherently a
    function of "now", and a stored value would just go stale. See the
    `freshness` property below.
    """

    __tablename__ = "memory_records"

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)

    type: Mapped[MemoryType] = mapped_column(SAEnum(MemoryType), index=True)
    scope: Mapped[MemoryScope] = mapped_column(SAEnum(MemoryScope), index=True)
    subject: Mapped[str]
    content: Mapped[str]
    structured_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    utility_score: Mapped[float] = mapped_column(Float, default=0.0)

    source_type: Mapped[str]
    source_id: Mapped[str | None] = mapped_column(default=None)
    evidence: Mapped[str | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    observed_at: Mapped[datetime] = mapped_column(default=utcnow)
    valid_from: Mapped[datetime] = mapped_column(default=utcnow)
    valid_until: Mapped[datetime | None] = mapped_column(default=None)

    last_accessed: Mapped[datetime | None] = mapped_column(default=None)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    successful_uses: Mapped[int] = mapped_column(Integer, default=0)
    failed_uses: Mapped[int] = mapped_column(Integer, default=0)

    supersedes: Mapped[str | None] = mapped_column(ForeignKey("memory_records.id"), default=None)
    superseded_by: Mapped[str | None] = mapped_column(default=None)

    status: Mapped[MemoryStatus] = mapped_column(
        SAEnum(MemoryStatus), default=MemoryStatus.CANDIDATE, index=True
    )
    sensitivity: Mapped[str] = mapped_column(default="internal")

    @property
    def is_current(self) -> bool:
        if self.status not in (MemoryStatus.CANDIDATE, MemoryStatus.CONFIRMED):
            return False
        return self.valid_until is None or _as_aware(self.valid_until) > utcnow()

    @property
    def freshness_days(self) -> float:
        return (utcnow() - _as_aware(self.updated_at)).total_seconds() / 86400
