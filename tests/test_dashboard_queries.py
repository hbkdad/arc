"""Tests for the hourly-bucketed dashboard queries (acr.dashboard.queries).

These back the overview page's activity sparklines -- the real behavior
worth locking in directly is the zero-fill: an hour with no rows must
still appear in the series as a real zero, not be silently absent.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.config import Settings
from acr.core.execution import run_task
from acr.dashboard import queries
from acr.providers.mock import MockProvider
from acr.telemetry.recorder import TelemetryRecorder


async def test_tasks_created_per_hour_zero_fills_every_hour_in_the_window(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    rows = await queries.tasks_created_per_hour(db_session, hours=6)

    assert len(rows) == 7  # every hour boundary in [now-6h, now], inclusive
    assert all(isinstance(count, int) for _, count in rows)
    assert all(count == 0 for _, count in rows)


async def test_tasks_created_per_hour_counts_a_real_task_in_the_current_bucket(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    rows = await queries.tasks_created_per_hour(db_session, hours=1)

    assert sum(count for _, count in rows) == 1
    # The real task landed in the *last* bucket (the current hour), not
    # silently dropped or misattributed to an earlier one.
    assert rows[-1][1] == 1


async def test_events_per_hour_zero_fills_every_hour_in_the_window(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    rows = await queries.events_per_hour(db_session, hours=6)

    assert len(rows) == 7
    assert all(count == 0 for _, count in rows)


async def test_events_per_hour_counts_real_telemetry_in_the_current_bucket(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    rows = await queries.events_per_hour(db_session, hours=1)

    assert sum(count for _, count in rows) > 0
    assert rows[-1][1] > 0


async def test_hourly_buckets_are_ordered_oldest_first(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    rows = await queries.tasks_created_per_hour(db_session, hours=3)

    labels = [label for label, _ in rows]
    assert labels == sorted(labels)
