"""Read-only aggregate queries backing the dashboard (master §1226-1239).

Every function here is a plain `SELECT` over an existing table — no new
decisions, scoring, or writes. The dashboard is a presentation layer over
subsystems that already exist; it must not grow a second copy of any
business logic those subsystems already own.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.topology import AgentTopologyRecord
from acr.benchmarks.models import BenchmarkRun
from acr.core.tasks.models import Task
from acr.memory.models import MemoryRecord
from acr.telemetry.models import TelemetryEvent

# Hourly buckets, not finer -- coarse enough that a sparkline over the
# default 24h window stays readable (24 points) without the caller having
# to downsample, fine enough to show real intraday activity shape.
_HOURLY_BUCKET = "%Y-%m-%dT%H:00:00"


def _hourly_buckets(since: datetime, until: datetime) -> list[str]:
    """Every hour boundary in [since, until], inclusive -- the *complete*
    x-axis a sparkline needs, independent of which hours actually have
    rows. Without this, an hour with zero activity would simply be
    missing from the series instead of plotting as a real zero, silently
    compressing the time axis."""
    start = since.replace(minute=0, second=0, microsecond=0)
    buckets = []
    cursor = start
    while cursor <= until:
        buckets.append(cursor.strftime(_HOURLY_BUCKET))
        cursor += timedelta(hours=1)
    return buckets


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


async def tasks_created_per_hour(
    session: AsyncSession, *, hours: int = 24
) -> list[tuple[str, int]]:
    """Real hourly task-creation counts for the last `hours` hours, as
    `(bucket_iso, count)` -- every hour boundary present (zero-filled),
    ordered oldest-first so a sparkline can render it left-to-right
    without the caller re-sorting."""
    until = datetime.now(UTC).replace(tzinfo=None)
    since = until - timedelta(hours=hours)
    bucket = func.strftime(_HOURLY_BUCKET, Task.created_at)
    stmt = select(bucket, func.count()).where(Task.created_at >= since).group_by(bucket)
    counts = {b: c for b, c in (await session.execute(stmt)).all()}
    return [(b, counts.get(b, 0)) for b in _hourly_buckets(since, until)]


async def events_per_hour(session: AsyncSession, *, hours: int = 24) -> list[tuple[str, int]]:
    """Same shape as `tasks_created_per_hour`, over `TelemetryEvent`."""
    until = datetime.now(UTC).replace(tzinfo=None)
    since = until - timedelta(hours=hours)
    bucket = func.strftime(_HOURLY_BUCKET, TelemetryEvent.created_at)
    stmt = select(bucket, func.count()).where(TelemetryEvent.created_at >= since).group_by(bucket)
    counts = {b: c for b, c in (await session.execute(stmt)).all()}
    return [(b, counts.get(b, 0)) for b in _hourly_buckets(since, until)]
