"""Benchmark case/result types and persistence (master §1061-1090).

`BenchmarkCase`/`CaseResult` are plain in-memory dataclasses — cases are
code, not state. `BenchmarkRun` is the one persisted record: the outcome of
running a named suite once, so a later run can be compared against it
(regression detection, this phase's other bullet).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from acr.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    id: str
    category: str
    description: str
    run: Callable[[], Awaitable[Any]]
    expected: Any


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    passed: bool
    score: float
    rationale: str


class BenchmarkRun(Base):
    """Master §1090: "Never publish fabricated benchmark results" — every
    row here is the outcome of actually executing a suite's cases."""

    __tablename__ = "benchmark_runs"

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)
    suite_name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    total_cases: Mapped[int]
    passed_cases: Mapped[int]
    score: Mapped[float]
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
