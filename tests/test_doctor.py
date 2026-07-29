"""Tests for acr.doctor health checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from acr.config import Settings
from acr.db.base import make_engine
from acr.doctor import (
    CheckStatus,
    check_data_dir,
    check_database,
    check_ollama_provider,
    check_python_version,
    run_checks,
)
from acr.providers.ollama import OllamaProvider


def test_check_python_version_is_ok_on_the_running_interpreter() -> None:
    result = check_python_version()
    assert result.status is CheckStatus.OK


def test_check_python_version_fails_below_the_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    import acr.doctor as doctor_module

    monkeypatch.setattr(doctor_module, "MIN_PYTHON", (99, 0))

    result = check_python_version()

    assert result.status is CheckStatus.FAIL
    assert "requires" in result.detail


def test_check_data_dir_creates_missing_directory(settings: Settings) -> None:
    result = check_data_dir(settings)
    assert result.status is CheckStatus.OK
    assert settings.data_dir.is_dir()


def test_check_data_dir_fails_cleanly_when_it_cannot_be_created(
    settings: Settings, tmp_path: Path
) -> None:
    # A regular file where a directory is expected: mkdir() must raise
    # NotADirectoryError/FileExistsError (both OSError) instead of the
    # unhandled traceback a naive caller might get.
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory")
    settings.data_dir = blocker / "acr"

    result = check_data_dir(settings)

    assert result.status is CheckStatus.FAIL
    assert "cannot create" in result.detail


async def test_check_database_fails_cleanly_when_the_db_path_is_unusable(
    settings: Settings,
) -> None:
    # A directory sitting where the database *file* should be: SQLite can
    # never open that as a database, on any platform, so this reliably
    # exercises the except-and-report-FAIL branch rather than hoping for a
    # platform-specific missing-path error.
    settings.ensure_data_dir()
    settings.database_path.mkdir()
    engine = make_engine(settings)

    try:
        result = await check_database(engine)
    finally:
        await engine.dispose()

    assert result.status is CheckStatus.FAIL
    assert result.name == "database"


async def _reachable(self: OllamaProvider) -> bool:
    return True


async def test_check_ollama_provider_hints_at_the_default_tier_setting_when_reachable(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Reachable but ACR still defaults to mock (default_min_quality_tier=0)
    # -- must surface the one-command fix rather than silently staying on
    # mock with no indication a real local model is sitting right there.
    monkeypatch.setattr(OllamaProvider, "is_available", _reachable)

    result = await check_ollama_provider(settings)

    assert result.status is CheckStatus.WARN
    assert "ACR_DEFAULT_MIN_QUALITY_TIER" in result.detail


async def test_check_ollama_provider_is_ok_when_reachable_and_tier_is_configured(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(OllamaProvider, "is_available", _reachable)
    settings.default_min_quality_tier = 1

    result = await check_ollama_provider(settings)

    assert result.status is CheckStatus.OK


async def test_run_checks_reports_python_data_dir_database_and_providers(
    settings: Settings,
) -> None:
    results = await run_checks(settings)

    by_name = {result.name: result for result in results}
    assert set(by_name) == {
        "python_version",
        "data_dir",
        "database",
        "provider_mock",
        "provider_ollama",
    }
    # Ollama is optional (may be WARN if not installed/running); everything
    # else must be OK, and nothing may be a hard FAIL.
    assert all(result.status is not CheckStatus.FAIL for result in results)
    assert by_name["provider_mock"].status is CheckStatus.OK
