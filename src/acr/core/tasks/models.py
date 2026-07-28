"""Task engine ORM models and lifecycle rules (master spec §948-967).

Lifecycle: CREATED -> PLANNING -> EXECUTING -> VERIFYING -> COMPLETED
                                        |            |
                                        v            v
                                     FAILED       (back to EXECUTING for retry)
Any non-terminal state can also move to CANCELLED.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acr.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED})

_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.CREATED: frozenset({TaskStatus.PLANNING, TaskStatus.CANCELLED}),
    TaskStatus.PLANNING: frozenset({TaskStatus.EXECUTING, TaskStatus.FAILED, TaskStatus.CANCELLED}),
    TaskStatus.EXECUTING: frozenset(
        {TaskStatus.VERIFYING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.VERIFYING: frozenset(
        {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.EXECUTING, TaskStatus.CANCELLED}
    ),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


class InvalidTransition(ValueError):
    """Raised when a task lifecycle transition is not permitted."""


def validate_transition(current: TaskStatus, target: TaskStatus) -> None:
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(f"cannot transition task from {current!s} to {target!s}")


class Task(Base):
    """A unit of work with a validated lifecycle (master §950, §959-967)."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)
    objective: Mapped[str]
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.CREATED)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    runs: Mapped[list[TaskRun]] = relationship(back_populates="task", cascade="all, delete-orphan")

    def transition(self, target: TaskStatus) -> None:
        validate_transition(self.status, target)
        self.status = target
        self.updated_at = _utcnow()

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


class TaskRun(Base):
    """One execution attempt of a Task against a specific provider."""

    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    provider_name: Mapped[str]
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.CREATED)
    started_at: Mapped[datetime] = mapped_column(default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(default=None)

    task: Mapped[Task] = relationship(back_populates="runs")
    steps: Mapped[list[Step]] = relationship(
        back_populates="task_run", cascade="all, delete-orphan", order_by="Step.index"
    )


class StepKind(StrEnum):
    ACTION = "action"
    OBSERVATION = "observation"


class Step(Base):
    """A single action taken, or observation received, within a TaskRun."""

    __tablename__ = "steps"

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)
    task_run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id"))
    index: Mapped[int]
    kind: Mapped[StepKind] = mapped_column(SAEnum(StepKind))
    name: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    task_run: Mapped[TaskRun] = relationship(back_populates="steps")
