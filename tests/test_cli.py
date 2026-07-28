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
