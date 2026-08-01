"""Tests for acr.dashboard (master §1225-1240)."""

from __future__ import annotations

from pathlib import Path

import pytest
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
    assert "No model calls recorded yet" in response.text


async def test_routing_page_shows_real_usage_after_a_task(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    response = _client(migrated_settings).get("/routing")

    assert response.status_code == 200
    assert "mock" in response.text
    assert "calls" in response.text.lower()
    body = response.text
    assert body.count("mock") >= 2  # once in the ladder table, once in usage


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
    assert 'id="theme-observatory"' in response.text
    assert ':root[data-theme="cyber"]' in response.text
    assert ':root[data-theme="observatory"]' in response.text
    # The toggle script must exist wherever the buttons do -- a page with
    # the buttons but no handler would render inert, unclickable controls.
    assert "setTheme" in response.text


async def test_observatory_theme_declares_its_own_display_font_and_texture(
    migrated_settings: Settings,
) -> None:
    response = _client(migrated_settings).get("/")

    observatory_block = response.text.split(':root[data-theme="observatory"]')[1].split("}")[0]
    assert "--display-font:" in observatory_block
    assert "Iowan Old Style" in observatory_block
    assert "--bg-texture:" in observatory_block
    assert "--bg-texture-size:" in observatory_block
    # h1/.brand must actually consume the new token -- declaring it with
    # nothing reading it would be a silent no-op.
    assert "font-family: var(--display-font)" in response.text


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


async def test_api_graph_derives_real_topology_edges_and_usage_nodes(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())
    await record_topology(
        db_session,
        task_class="ui-audit",
        worker_count=1,
        model_names=["mock"],
        skill_ids=["dashboard-ui-audit", "ui-design-critique"],
        total_tokens=120,
        cost_estimate=0.02,
        quality_score=1.0,
        succeeded=True,
    )
    await db_session.commit()

    response = _client(migrated_settings).get("/api/graph")

    assert response.status_code == 200
    body = response.json()
    assert {"id": "ui-audit", "count": 1, "succeeded_count": 1} in body["task_classes"]
    assert {"id": "dashboard-ui-audit", "count": 1} in body["skills"]
    assert {"id": "ui-design-critique", "count": 1} in body["skills"]
    model = next(m for m in body["models"] if m["name"] == "mock")
    assert model["call_count"] >= 1  # from the real run_task() model.call.completed event
    assert model["estimated_cost"] is not None
    assert {
        "source": "taskclass:ui-audit",
        "target": "skill:dashboard-ui-audit",
        "kind": "uses_skill",
    } in body["edges"]
    model_edge = next(
        e for e in body["edges"] if e["kind"] == "uses_model" and e["target"] == "model:mock"
    )
    assert model_edge["tokens"] == 120
    assert model_edge["cost"] == 0.02


async def test_api_graph_is_empty_but_valid_with_no_data(migrated_settings: Settings) -> None:
    response = _client(migrated_settings).get("/api/graph")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "memory_types": [],
        "tasks": [],
        "agents": [],
        "events": [],
        "task_classes": [],
        "skills": [],
        "models": [],
        "edges": [],
    }


async def test_overview_page_renders_activity_sparkline_charts(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    response = _client(migrated_settings).get("/")

    assert response.status_code == 200
    assert 'id="chart-tasks-hourly"' in response.text
    assert 'id="chart-events-hourly"' in response.text
    assert "tasks-per-hour-data" in response.text


async def test_memory_page_renders_type_chart_and_calibration_section(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await remember(
        db_session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject="acr.dashboard.chart-test",
            content="a memory record for the type-chart test",
            source_type="session",
            confidence=0.9,
            evidence="observed directly",
        ),
    )
    await db_session.commit()

    response = _client(migrated_settings).get("/memory")

    assert response.status_code == 200
    assert 'id="chart-memory-types"' in response.text
    assert "Confidence calibration" in response.text
    assert 'id="chart-calibration"' in response.text
    # No record has any recorded successful/failed use yet -- the
    # empty-calibration branch, not a fabricated reliability curve.
    assert "0 record(s) considered" in response.text


async def test_memory_page_calibration_reflects_real_recorded_outcomes(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    _evaluation, record = await remember(
        db_session,
        MemoryCandidate(
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.PROJECT,
            subject="acr.dashboard.calibration-test",
            content="a memory record with real recorded outcomes",
            source_type="session",
            confidence=0.9,
            evidence="observed directly",
        ),
    )
    assert record is not None
    record.successful_uses = 4
    record.failed_uses = 1
    await db_session.commit()

    response = _client(migrated_settings).get("/memory")

    assert response.status_code == 200
    assert "1 record(s) considered" in response.text
    assert "Brier score" in response.text


async def test_routing_page_renders_usage_charts_after_a_task(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    response = _client(migrated_settings).get("/routing")

    assert response.status_code == 200
    assert 'id="chart-usage-calls"' in response.text
    assert 'id="chart-usage-cost"' in response.text


async def test_visualization_page_renders_the_view_toggle_and_timeline_canvas(
    migrated_settings: Settings,
) -> None:
    response = _client(migrated_settings).get("/visualization")

    assert response.status_code == 200
    assert 'id="view-graph"' in response.text
    assert 'id="view-timeline"' in response.text
    assert '<canvas id="timeline"' in response.text


async def test_api_graph_tasks_include_created_at_for_the_timeline_view(
    migrated_settings: Settings, db_session: AsyncSession
) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    response = _client(migrated_settings).get("/api/graph")

    assert response.status_code == 200
    body = response.json()
    assert body["tasks"]
    for task in body["tasks"]:
        assert "created_at" in task
        assert "updated_at" in task


async def test_charts_js_static_asset_is_served(migrated_settings: Settings) -> None:
    response = _client(migrated_settings).get("/static/charts.js")

    assert response.status_code == 200
    assert "ACRCharts" in response.text


async def test_charts_js_loads_before_page_content_that_calls_it(
    migrated_settings: Settings,
) -> None:
    # charts.js must appear before {% block content %} in base.html --
    # every chart-rendering page has an inline <script> inside that block
    # that calls ACRCharts.* synchronously at parse time, so loading the
    # library after the content block (as tables.js does, safely, since
    # it only reacts to already-rendered tables) would leave every chart
    # blank with no error surfaced to the user.
    response = _client(migrated_settings).get("/")

    charts_pos = response.text.index('src="/static/charts.js"')
    content_pos = response.text.index('id="chart-tasks-hourly"')
    assert charts_pos < content_pos


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


def _isolate_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """`/settings` reads/writes `.env` relative to CWD (same as `acr setup`
    and pydantic-settings' own `env_file=".env"`) -- chdir into a scratch
    dir so a test never touches this repo's real `.env`."""
    monkeypatch.chdir(tmp_path)
    return tmp_path / ".env"


async def test_settings_page_shows_not_configured_when_no_keys_set(
    migrated_settings: Settings,
) -> None:
    response = _client(migrated_settings).get("/settings")

    assert response.status_code == 200
    assert "not configured" in response.text
    # A key must never be echoed back into the page, configured or not.
    assert migrated_settings.anthropic_api_key is None


async def test_settings_page_shows_configured_pill_for_an_existing_key(
    migrated_settings: Settings,
) -> None:
    migrated_settings.anthropic_api_key = "sk-ant-already-set"

    response = _client(migrated_settings).get("/settings")

    assert response.status_code == 200
    # Exact pill class, not a loose "configured" substring match -- "not
    # configured" (the OpenAI field, still unset) also contains the
    # substring "configured", so a bare `in` check can't actually tell
    # the two pill states apart.
    assert '<span class="pill pill-ok">configured</span>' in response.text
    assert '<span class="pill pill-danger">not configured</span>' in response.text
    # The real key value is never rendered anywhere in the page.
    assert "sk-ant-already-set" not in response.text


async def test_settings_post_writes_key_to_env_file_and_updates_live_settings(
    migrated_settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_path = _isolate_env_file(monkeypatch, tmp_path)

    response = _client(migrated_settings).post(
        "/settings", json={"anthropic_api_key": "sk-ant-fresh-key"}
    )

    assert response.status_code == 200
    assert "ACR_ANTHROPIC_API_KEY=sk-ant-fresh-key" in env_path.read_text(encoding="utf-8")
    # Live: the *same* Settings instance the running app holds is updated
    # in place, no restart needed.
    assert migrated_settings.anthropic_api_key == "sk-ant-fresh-key"


async def test_settings_post_writes_openai_key_to_env_file_and_updates_live_settings(
    migrated_settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The Anthropic branch above is a near-identical copy-paste of this
    # one in settings_update() -- without its own test, a typo'd env var
    # name or wrong settings attribute in *this* branch specifically
    # would pass CI silently.
    env_path = _isolate_env_file(monkeypatch, tmp_path)

    response = _client(migrated_settings).post("/settings", json={"openai_api_key": "sk-fresh-key"})

    assert response.status_code == 200
    assert "ACR_OPENAI_API_KEY=sk-fresh-key" in env_path.read_text(encoding="utf-8")
    assert migrated_settings.openai_api_key == "sk-fresh-key"


async def test_settings_post_with_a_blank_field_does_not_clear_an_existing_key(
    migrated_settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_env_file(monkeypatch, tmp_path)
    migrated_settings.anthropic_api_key = "sk-ant-keep-me"

    response = _client(migrated_settings).post("/settings", json={"anthropic_api_key": ""})

    assert response.status_code == 200
    assert migrated_settings.anthropic_api_key == "sk-ant-keep-me"


async def test_settings_post_enable_default_cloud_routing_raises_the_tier(
    migrated_settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_path = _isolate_env_file(monkeypatch, tmp_path)
    assert migrated_settings.default_min_quality_tier == 0

    response = _client(migrated_settings).post(
        "/settings", json={"enable_default_cloud_routing": True}
    )

    assert response.status_code == 200
    assert migrated_settings.default_min_quality_tier == 2
    assert "ACR_DEFAULT_MIN_QUALITY_TIER=2" in env_path.read_text(encoding="utf-8")


async def test_settings_post_enable_default_cloud_routing_is_a_noop_once_already_on(
    migrated_settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_path = _isolate_env_file(monkeypatch, tmp_path)
    migrated_settings.default_min_quality_tier = 2

    response = _client(migrated_settings).post(
        "/settings", json={"enable_default_cloud_routing": True}
    )

    assert response.status_code == 200
    assert migrated_settings.default_min_quality_tier == 2
    # No redundant write -- the guard (`< 2`) must actually skip set_var(),
    # not just skip re-mutating the in-memory value.
    assert not env_path.exists() or "ACR_DEFAULT_MIN_QUALITY_TIER" not in env_path.read_text(
        encoding="utf-8"
    )


async def test_settings_post_rejects_a_cross_origin_request(
    migrated_settings: Settings,
) -> None:
    response = _client(migrated_settings).post(
        "/settings",
        json={"anthropic_api_key": "sk-ant-attacker-key"},
        headers={"origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert migrated_settings.anthropic_api_key is None


async def test_settings_post_allows_a_same_origin_request(
    migrated_settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_env_file(monkeypatch, tmp_path)
    client = _client(migrated_settings)

    response = client.post(
        "/settings",
        json={"anthropic_api_key": "sk-ant-fresh-key"},
        headers={"origin": str(client.base_url)},
    )

    assert response.status_code == 200
    assert migrated_settings.anthropic_api_key == "sk-ant-fresh-key"


async def test_settings_saved_banner_shown_after_redirect(migrated_settings: Settings) -> None:
    response = _client(migrated_settings).get("/settings", params={"saved": "1"})

    assert response.status_code == 200
    assert "Settings saved" in response.text
