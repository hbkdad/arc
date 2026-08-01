"""Tests for acr.env_config."""

from __future__ import annotations

from pathlib import Path

import pytest

from acr.env_config import ensure_env_file, has_var, set_var


def test_ensure_env_file_creates_an_empty_file_with_no_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ensure_env_file() seeds from a `.env.example` relative to CWD if one
    # exists (matching `acr setup`'s original behavior) -- chdir so this
    # test exercises the true "nothing to seed from" branch instead of
    # picking up this repo's own real .env.example.
    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / ".env"

    ensure_env_file(env_path)

    assert env_path.exists()
    assert env_path.read_text(encoding="utf-8") == ""


def test_ensure_env_file_does_not_touch_an_existing_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("ACR_LOG_LEVEL=DEBUG\n", encoding="utf-8")

    ensure_env_file(env_path)

    assert env_path.read_text(encoding="utf-8") == "ACR_LOG_LEVEL=DEBUG\n"


def test_has_var_true_only_for_a_non_empty_assignment() -> None:
    text = "ACR_ANTHROPIC_API_KEY=sk-ant-real\nACR_OPENAI_API_KEY=\n"
    assert has_var(text, "ACR_ANTHROPIC_API_KEY") is True
    assert has_var(text, "ACR_OPENAI_API_KEY") is False
    assert has_var(text, "ACR_MISSING") is False


def test_set_var_appends_a_new_variable(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("ACR_LOG_LEVEL=DEBUG\n", encoding="utf-8")

    set_var(env_path, "ACR_ANTHROPIC_API_KEY", "sk-ant-new")

    content = env_path.read_text(encoding="utf-8")
    assert "ACR_LOG_LEVEL=DEBUG" in content
    assert "ACR_ANTHROPIC_API_KEY=sk-ant-new" in content


def test_set_var_replaces_an_existing_assignment_in_place(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("ACR_ANTHROPIC_API_KEY=old-key\nACR_LOG_LEVEL=DEBUG\n", encoding="utf-8")

    set_var(env_path, "ACR_ANTHROPIC_API_KEY", "new-key")

    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert lines.count("ACR_ANTHROPIC_API_KEY=new-key") == 1
    assert "ACR_ANTHROPIC_API_KEY=old-key" not in lines
    assert "ACR_LOG_LEVEL=DEBUG" in lines


def test_set_var_creates_the_env_file_if_missing(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"

    set_var(env_path, "ACR_OPENAI_API_KEY", "sk-new")

    assert "ACR_OPENAI_API_KEY=sk-new" in env_path.read_text(encoding="utf-8")
