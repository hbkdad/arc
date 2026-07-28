"""Tests for acr.dashboard (master §1225-1240)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.topology import record_topology
from acr.benchmarks import memory_recall
from acr.benchmarks.runner import run_suite
from acr.config import Settings
from acr.core.execution import run_task
from acr.dashboard.app import create_app
from acr.evaluation.evaluators import ExactMatchEvaluator
from acr.memory import MemoryCandidate, MemoryScope, MemoryType
from acr.memory.write_controller import remember
from acr.providers.mock import MockProvider
from acr.security.audit import record_audit_event
from acr.skills.registry import register
from acr.telemetry.recorder import TelemetryRecorder

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


def _client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


async def test_overview_shows_system_health_and_task_activity(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    response = _client(migrated_settings).get("/")

    assert response.status_code == 200
    assert "System health" in response.text
    assert "completed" in response.text
    assert "task.created" in response.text


async def test_tasks_page_lists_recent_tasks(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await run_task(db_session, "diagnose the database", MockProvider(), TelemetryRecorder())

    response = _client(migrated_settings).get("/tasks")

    assert response.status_code == 200
    assert "diagnose the database" in response.text


async def test_tasks_page_renders_with_no_tasks(migrated_settings: Settings) -> None:
    response = _client(migrated_settings).get("/tasks")

    assert response.status_code == 200
    assert "No tasks recorded yet" in response.text


async def test_agents_page_lists_topology_records(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await record_topology(
        db_session,
        task_class="research",
        worker_count=2,
        model_names=["mock"],
        skill_ids=["skill-a"],
    )
    await db_session.commit()

    response = _client(migrated_settings).get("/agents")

    assert response.status_code == 200
    assert "research" in response.text
    assert "skill-a" in response.text


async def test_memory_page_shows_counts_and_recent_records(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await remember(
        db_session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject="acr.dashboard",
            content="The dashboard is a read-only presentation layer.",
            source_type="session",
            confidence=0.9,
            evidence="observed directly",
        ),
    )
    await db_session.commit()

    response = _client(migrated_settings).get("/memory")

    assert response.status_code == 200
    assert "acr.dashboard" in response.text
    assert "semantic" in response.text


async def test_skills_page_lists_registered_skills(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await register(db_session, FIXTURES / "sqlite-diagnostics")
    await db_session.commit()

    response = _client(migrated_settings).get("/skills")

    assert response.status_code == 200
    assert "sqlite-diagnostics" in response.text or "SQLite" in response.text


async def test_tools_page_lists_registered_tools(migrated_settings: Settings) -> None:
    response = _client(migrated_settings).get("/tools")

    assert response.status_code == 200
    assert "memory_search" in response.text
    assert "skill_search" in response.text


async def test_routing_page_lists_the_default_ladder(migrated_settings: Settings) -> None:
    response = _client(migrated_settings).get("/routing")

    assert response.status_code == 200
    assert "mock" in response.text
    assert "available" in response.text


async def test_security_page_lists_recent_audit_events(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await record_audit_event(
        db_session,
        TelemetryRecorder(),
        action="tool.invoke:memory_search",
        outcome="granted",
    )
    await db_session.commit()

    response = _client(migrated_settings).get("/security")

    assert response.status_code == 200
    assert "tool.invoke:memory_search" in response.text
    assert "granted" in response.text


async def test_benchmarks_page_lists_recent_runs(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await memory_recall.seed(db_session)
    cases = memory_recall.build_cases(db_session)
    await run_suite(db_session, memory_recall.SUITE_NAME, cases, ExactMatchEvaluator())
    await db_session.commit()

    response = _client(migrated_settings).get("/benchmarks")

    assert response.status_code == 200
    assert memory_recall.SUITE_NAME in response.text


async def test_events_page_filters_by_event_type(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    client = _client(migrated_settings)
    unfiltered = client.get("/events")
    filtered = client.get("/events", params={"event_type": "task.created"})

    assert unfiltered.status_code == 200
    assert filtered.status_code == 200
    assert "<code>task.created</code>" in filtered.text
    assert "<code>model.call.completed</code>" not in filtered.text
