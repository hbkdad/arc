"""Tests for acr.config.Settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from acr.config import Settings


def test_database_url_points_at_sqlite_file_in_data_dir(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    assert settings.database_url == f"sqlite+aiosqlite:///{(tmp_path / 'acr.db').as_posix()}"


def test_ensure_data_dir_creates_nested_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "acr"
    settings = Settings(data_dir=target)
    assert not target.exists()

    created = settings.ensure_data_dir()

    assert created == target
    assert target.is_dir()


def test_env_vars_override_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ACR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ACR_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ACR_LOG_FORMAT", "console")

    settings = Settings()

    assert settings.data_dir == tmp_path
    assert settings.log_level == "DEBUG"
    assert settings.log_format == "console"
