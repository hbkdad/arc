"""Skill package format (master §645-660).

A skill is a directory containing at minimum `SKILL.yaml`. The full package
shape master §647-653 describes (`instructions.md`, `examples/`, `tests/`,
`scripts/`, `assets/`, `history.jsonl`) is honored where present but only
`SKILL.yaml` is required — the others are optional content a skill package
may or may not use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

MANIFEST_FILENAME = "SKILL.yaml"
INSTRUCTIONS_FILENAME = "instructions.md"


class SkillFormatError(ValueError):
    """Raised when a skill package is missing or its manifest is invalid."""


class SkillManifest(BaseModel):
    """The exact required metadata set from master §655-676."""

    id: str
    name: str
    version: str
    description: str
    task_classes: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    token_estimate: int = 0
    applicability: str = ""
    contraindications: str = ""
    verification: str = ""
    origin: str = "manual"
    author: str = ""


def load_manifest(skill_dir: Path) -> SkillManifest:
    """Load and validate `SKILL.yaml` from `skill_dir`."""
    manifest_path = skill_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise SkillFormatError(f"{manifest_path} does not exist")

    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SkillFormatError(f"{manifest_path} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise SkillFormatError(f"{manifest_path} must contain a YAML mapping")

    try:
        return SkillManifest.model_validate(raw)
    except ValidationError as exc:
        raise SkillFormatError(f"{manifest_path} failed validation: {exc}") from exc


def load_instructions(skill_dir: Path) -> str | None:
    """Read `instructions.md` if the package has one."""
    instructions_path = skill_dir / INSTRUCTIONS_FILENAME
    if not instructions_path.is_file():
        return None
    return instructions_path.read_text(encoding="utf-8")
