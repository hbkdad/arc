"""Tests for acr.skills.format (master §645-660)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

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


def _write_manifest_with_id(skill_dir: Path, skill_id: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"id": skill_id, "name": "x", "version": "1.0.0", "description": "x"}
    (skill_dir / "SKILL.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")


@pytest.mark.parametrize(
    "bad_id",
    [
        "../../../etc/passwd",
        "../escape",
        "a/../../b",
        "/absolute/path",
        "a\\b",
        "..",
    ],
)
def test_load_manifest_rejects_a_path_traversal_id(tmp_path: Path, bad_id: str) -> None:
    # create_candidate_version() builds a directory path directly from this
    # id (data_dir / "generated_skills" / f"{id}@vN") with no further
    # sanitization -- an id like "../../../etc/passwd" registered from an
    # untrusted skill package would let a later `acr skills evolve` write
    # outside the intended directory.
    skill_dir = tmp_path / "skill"
    _write_manifest_with_id(skill_dir, bad_id)

    with pytest.raises(SkillFormatError, match="failed validation"):
        load_manifest(skill_dir)


@pytest.mark.parametrize("good_id", ["sqlite-diagnostics", "sqlite-diagnostics@v2", "a.b_c-1"])
def test_load_manifest_accepts_real_id_shapes(tmp_path: Path, good_id: str) -> None:
    skill_dir = tmp_path / "skill"
    _write_manifest_with_id(skill_dir, good_id)

    assert load_manifest(skill_dir).id == good_id
