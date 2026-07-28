"""Read-only aggregate queries backing the dashboard (master §1226-1239).

Every function here is a plain `SELECT` over an existing table — no new
decisions, scoring, or writes. The dashboard is a presentation layer over
subsystems that already exist; it must not grow a second copy of any
business logic those subsystems already own.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.topology import AgentTopologyRecord
from acr.benchmarks.models import BenchmarkRun
from acr.core.tasks.models import Task
from acr.memory.models import MemoryRecord
from acr.telemetry.models import TelemetryEvent


async def recent_tasks(session: AsyncSession, *, limit: int = 20) -> list[Task]:
    stmt = select(Task).order_by(Task.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def task_status_counts(session: AsyncSession) -> dict[str, int]:
    stmt = select(Task.status, func.count()).group_by(Task.status)
    return {status.value: count for status, count in (await session.execute(stmt)).all()}


async def recent_topology(session: AsyncSession, *, limit: int = 20) -> list[AgentTopologyRecord]:
    stmt = select(AgentTopologyRecord).order_by(AgentTopologyRecord.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def memory_type_counts(session: AsyncSession) -> dict[str, int]:
    stmt = select(MemoryRecord.type, func.count()).group_by(MemoryRecord.type)
    return {type_.value: count for type_, count in (await session.execute(stmt)).all()}


async def memory_status_counts(session: AsyncSession) -> dict[str, int]:
    stmt = select(MemoryRecord.status, func.count()).group_by(MemoryRecord.status)
    return {status.value: count for status, count in (await session.execute(stmt)).all()}


async def recent_memories(session: AsyncSession, *, limit: int = 20) -> list[MemoryRecord]:
    stmt = select(MemoryRecord).order_by(MemoryRecord.updated_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def recent_benchmark_runs(session: AsyncSession, *, limit: int = 20) -> list[BenchmarkRun]:
    stmt = select(BenchmarkRun).order_by(BenchmarkRun.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def recent_events(
    session: AsyncSession, *, event_type: str | None = None, limit: int = 50
) -> list[TelemetryEvent]:
    stmt = select(TelemetryEvent).order_by(TelemetryEvent.created_at.desc()).limit(limit)
    if event_type is not None:
        stmt = stmt.where(TelemetryEvent.event_type == event_type)
    return list((await session.execute(stmt)).scalars().all())


async def event_type_counts(session: AsyncSession) -> dict[str, int]:
    stmt = select(TelemetryEvent.event_type, func.count()).group_by(TelemetryEvent.event_type)
    return {event_type: count for event_type, count in (await session.execute(stmt)).all()}
