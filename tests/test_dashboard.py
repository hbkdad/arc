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
from acr.dashboard.app import _pill_class, create_app
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


def test_pill_class_maps_known_statuses_to_semantic_classes() -> None:
    assert _pill_class("completed") == "pill-ok"
    assert _pill_class("failed") == "pill-danger"
    assert _pill_class("pending") == "pill-warn"
    assert _pill_class("executing") == "pill-info"
    assert _pill_class("archived") == "pill-neutral"


def test_pill_class_unwraps_an_enum_and_is_case_insensitive() -> None:
    from acr.core.tasks.models import TaskStatus

    assert _pill_class(TaskStatus.COMPLETED) == "pill-ok"
    assert _pill_class("COMPLETED") == "pill-ok"


def test_pill_class_falls_back_to_neutral_for_an_unknown_value() -> None:
    assert _pill_class("some-未知-value") == "pill-neutral"


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


async def test_proposals_page_lists_a_real_proposal(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    from acr.learning.proposals import propose_skill_evolution
    from acr.skills.evolution import create_candidate_version
    from acr.skills.models import SkillStatus
    from acr.skills.registry import set_status

    baseline = await register(db_session, FIXTURES / "sqlite-diagnostics")
    baseline = await set_status(db_session, baseline.id, SkillStatus.ACTIVE)
    candidate = await create_candidate_version(db_session, tmp_path, baseline, {})
    await db_session.commit()

    proposal = await propose_skill_evolution(
        db_session,
        migrated_settings,
        TelemetryRecorder(),
        baseline_id=baseline.id,
        candidate_id=candidate.id,
    )
    await db_session.commit()
    assert proposal is not None

    response = _client(migrated_settings).get("/proposals")

    assert response.status_code == 200
    assert "skill_evolution_promotion" in response.text
    assert baseline.id in response.text


async def test_proposals_page_renders_with_none_yet(migrated_settings: Settings) -> None:
    response = _client(migrated_settings).get("/proposals")

    assert response.status_code == 200
    assert "No proposals yet" in response.text


async def test_tables_js_static_asset_is_served(migrated_settings: Settings) -> None:
    response = _client(migrated_settings).get("/static/tables.js")

    assert response.status_code == 200
    assert "table-filter" in response.text


async def test_overview_page_loads_the_table_sort_and_filter_script(
    migrated_settings: Settings,
) -> None:
    response = _client(migrated_settings).get("/")

    assert response.status_code == 200
    assert '<script src="/static/tables.js"></script>' in response.text


async def test_overview_page_offers_a_neo_cyber_theme_toggle(
    migrated_settings: Settings,
) -> None:
    response = _client(migrated_settings).get("/")

    assert response.status_code == 200
    assert 'id="theme-cyber"' in response.text
    assert 'id="theme-default"' in response.text
    assert ':root[data-theme="cyber"]' in response.text
    # The toggle script must exist wherever the buttons do -- a page with
    # the buttons but no handler would render inert, unclickable controls.
    assert "setTheme" in response.text


async def test_visualization_page_renders_the_canvas_and_script(
    migrated_settings: Settings,
) -> None:
    response = _client(migrated_settings).get("/visualization")

    assert response.status_code == 200
    assert '<canvas id="graph"' in response.text
    assert "/static/visualization.js" in response.text


async def test_visualization_static_asset_is_served(migrated_settings: Settings) -> None:
    response = _client(migrated_settings).get("/static/visualization.js")

    assert response.status_code == 200
    assert "api/graph" in response.text


async def test_api_graph_reflects_real_seeded_data(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())
    await remember(
        db_session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject="acr.dashboard",
            content="graph data comes from real queries",
            source_type="session",
            confidence=0.9,
            evidence="observed directly",
        ),
    )
    await record_topology(
        db_session,
        task_class="research",
        worker_count=2,
        model_names=["mock"],
        skill_ids=[],
        quality_score=0.75,
        succeeded=True,
    )
    await db_session.commit()

    response = _client(migrated_settings).get("/api/graph")

    assert response.status_code == 200
    body = response.json()
    assert {"type": "semantic", "count": 1} in body["memory_types"]
    assert any(t["objective"] == "say hello" for t in body["tasks"])
    assert any(a["task_class"] == "research" and a["succeeded"] is True for a in body["agents"])
    assert any(e["event_type"] == "task.created" for e in body["events"])


async def test_api_graph_is_empty_but_valid_with_no_data(migrated_settings: Settings) -> None:
    response = _client(migrated_settings).get("/api/graph")

    assert response.status_code == 200
    body = response.json()
    assert body == {"memory_types": [], "tasks": [], "agents": [], "events": []}


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
