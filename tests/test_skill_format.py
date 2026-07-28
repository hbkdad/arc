"""Tests for acr.skills.format (master §645-660)."""

from __future__ import annotations

from pathlib import Path

import pytest

from acr.skills.format import SkillFormatError, load_instructions, load_manifest

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


def test_load_manifest_parses_a_valid_skill() -> None:
    manifest = load_manifest(FIXTURES / "sqlite-diagnostics")

    assert manifest.id == "sqlite-diagnostics"
    assert manifest.version == "1.0.0"
    assert "database-diagnostics" in manifest.task_classes
    assert manifest.token_estimate == 400


def test_load_manifest_raises_for_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(SkillFormatError, match="does not exist"):
        load_manifest(tmp_path / "nonexistent")


def test_load_manifest_raises_for_invalid_manifest() -> None:
    with pytest.raises(SkillFormatError, match="failed validation"):
        load_manifest(FIXTURES / "broken-skill")


def test_load_instructions_reads_markdown_when_present() -> None:
    text = load_instructions(FIXTURES / "sqlite-diagnostics")
    assert text is not None
    assert "PRAGMA integrity_check" in text


def test_load_instructions_returns_none_when_absent() -> None:
    assert load_instructions(FIXTURES / "broken-skill") is None
