"""Skill registry schema (master §645-683).

`SkillRecord` is the DB-backed registry entry for a skill package living on
disk at `path`. The manifest fields are duplicated into columns (rather than
re-parsing `SKILL.yaml` on every lookup) precisely so skills are
"discoverable without loading every skill into context" (master §683) — a
metadata query never touches the filesystem.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from acr.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class SkillStatus(StrEnum):
    EXPERIMENTAL = "experimental"
    QUARANTINED = "quarantined"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


TERMINAL_STATUSES = frozenset({SkillStatus.RETIRED})

_ALLOWED_TRANSITIONS: dict[SkillStatus, frozenset[SkillStatus]] = {
    SkillStatus.EXPERIMENTAL: frozenset({SkillStatus.QUARANTINED, SkillStatus.ACTIVE}),
    SkillStatus.QUARANTINED: frozenset({SkillStatus.ACTIVE, SkillStatus.RETIRED}),
    SkillStatus.ACTIVE: frozenset({SkillStatus.DEPRECATED, SkillStatus.QUARANTINED}),
    SkillStatus.DEPRECATED: frozenset({SkillStatus.RETIRED, SkillStatus.ACTIVE}),
    SkillStatus.RETIRED: frozenset(),
}


class InvalidSkillTransition(ValueError):
    """Raised when a skill status transition is not permitted."""


def validate_transition(current: SkillStatus, target: SkillStatus) -> None:
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidSkillTransition(f"cannot transition skill from {current!s} to {target!s}")


class SkillRecord(Base):
    """A skill's registry entry (master §655-676)."""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(primary_key=True)  # manifest `id` — stable, human-chosen
    name: Mapped[str]
    version: Mapped[str]
    description: Mapped[str]
    task_classes: Mapped[list[str]] = mapped_column(JSON, default=list)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    dependencies: Mapped[list[str]] = mapped_column(JSON, default=list)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    tools: Mapped[list[str]] = mapped_column(JSON, default=list)
    models: Mapped[list[str]] = mapped_column(JSON, default=list)
    token_estimate: Mapped[int] = mapped_column(default=0)
    applicability: Mapped[str] = mapped_column(default="")
    contraindications: Mapped[str] = mapped_column(default="")
    verification: Mapped[str] = mapped_column(default="")
    origin: Mapped[str] = mapped_column(default="manual")
    author: Mapped[str] = mapped_column(default="")
    path: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    status: Mapped[SkillStatus] = mapped_column(
        SAEnum(SkillStatus), default=SkillStatus.EXPERIMENTAL
    )
    reliability: Mapped[float] = mapped_column(default=0.0)
    successful_uses: Mapped[int] = mapped_column(default=0)
    failed_uses: Mapped[int] = mapped_column(default=0)

    def transition(self, target: SkillStatus) -> None:
        validate_transition(self.status, target)
        self.status = target
        self.updated_at = utcnow()
