"""Tests for the `acr` CLI (Typer app)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from acr.cli import app
from acr.config import Settings

runner = CliRunner()


def test_version_command_prints_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip()


def test_doctor_command_succeeds_in_isolated_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ACR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ACR_LOG_FORMAT", "console")
    from acr.config import get_settings

    get_settings.cache_clear()

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "python_version" in result.stdout
    assert "data_dir" in result.stdout
    assert "database" in result.stdout
    assert "provider_mock" in result.stdout
    assert "provider_ollama" in result.stdout

    get_settings.cache_clear()


def test_run_command_creates_and_completes_task(migrated_settings: Settings) -> None:
    result = runner.invoke(app, ["run", "hello there"])

    assert result.exit_code == 0
    assert "completed" in result.stdout


_FIXTURE_SKILL = Path(__file__).parent / "fixtures" / "skills" / "sqlite-diagnostics"


def test_skills_register_then_list(migrated_settings: Settings) -> None:
    register_result = runner.invoke(app, ["skills", "register", str(_FIXTURE_SKILL)])
    assert register_result.exit_code == 0
    assert "sqlite-diagnostics" in register_result.stdout
    assert "experimental" in register_result.stdout

    list_result = runner.invoke(app, ["skills", "list"])
    assert list_result.exit_code == 0
    assert "sqlite-diagnostics" in list_result.stdout


def test_skills_activate_transitions_status(migrated_settings: Settings) -> None:
    runner.invoke(app, ["skills", "register", str(_FIXTURE_SKILL)])

    result = runner.invoke(app, ["skills", "activate", "sqlite-diagnostics", "--status", "active"])

    assert result.exit_code == 0
    assert "active" in result.stdout


def test_skills_search_and_route(migrated_settings: Settings) -> None:
    runner.invoke(app, ["skills", "register", str(_FIXTURE_SKILL)])
    runner.invoke(app, ["skills", "activate", "sqlite-diagnostics", "--status", "active"])

    search_result = runner.invoke(app, ["skills", "search", "SQLite"])
    assert search_result.exit_code == 0
    assert "sqlite-diagnostics" in search_result.stdout

    route_result = runner.invoke(
        app, ["skills", "route", "Diagnose a SQLite database integrity issue"]
    )
    assert route_result.exit_code == 0
    assert "sqlite-diagnostics" in route_result.stdout


def test_benchmark_run_and_history(migrated_settings: Settings) -> None:
    first = runner.invoke(app, ["benchmark", "run", "memory-recall"])
    assert first.exit_code == 0
    assert "memory-recall" in first.stdout

    second = runner.invoke(app, ["benchmark", "run", "memory-recall"])
    assert second.exit_code == 0

    history = runner.invoke(app, ["benchmark", "history", "memory-recall"])
    assert history.exit_code == 0
    assert "score" in history.stdout


def test_benchmark_run_rejects_unknown_suite(migrated_settings: Settings) -> None:
    result = runner.invoke(app, ["benchmark", "run", "does-not-exist"])
    assert result.exit_code == 1
    assert "unknown suite" in result.stdout


def test_waste_commands_run_cleanly_with_no_history(migrated_settings: Settings) -> None:
    duplicates = runner.invoke(app, ["waste", "duplicates"])
    assert duplicates.exit_code == 0
    assert "no duplicate" in duplicates.stdout

    utilization = runner.invoke(app, ["waste", "utilization"])
    assert utilization.exit_code == 0
    assert "utilization=" in utilization.stdout
