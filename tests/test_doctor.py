"""Tests for acr.doctor health checks."""

from __future__ import annotations

from acr.config import Settings
from acr.doctor import CheckStatus, check_data_dir, check_python_version, run_checks


def test_check_python_version_is_ok_on_the_running_interpreter() -> None:
    result = check_python_version()
    assert result.status is CheckStatus.OK


def test_check_data_dir_creates_missing_directory(settings: Settings) -> None:
    result = check_data_dir(settings)
    assert result.status is CheckStatus.OK
    assert settings.data_dir.is_dir()


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
