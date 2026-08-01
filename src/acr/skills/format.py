"""Skill package format (master §645-660).

A skill is a directory containing at minimum `SKILL.yaml`. The full package
shape master §647-653 describes (`instructions.md`, `examples/`, `tests/`,
`scripts/`, `assets/`, `history.jsonl`) is honored where present but only
`SKILL.yaml` is required — the others are optional content a skill package
may or may not use.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

MANIFEST_FILENAME = "SKILL.yaml"
INSTRUCTIONS_FILENAME = "instructions.md"

# `id` becomes a path segment: skills.evolution.create_candidate_version()
# writes `data_dir / "generated_skills" / f"{id}@v{n}"` with no further
# sanitization. Without this, a skill package registered with an id like
# "../../../whatever" (a shared/downloaded package, not necessarily one
# authored locally) would let a later `acr skills evolve` write a new
# SKILL.yaml outside the intended directory -- an attacker-controlled file
# write anywhere the process has permissions.
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]*$")


class SkillFormatError(ValueError):
    """Raised when a skill package is missing or its manifest is invalid."""


class SkillManifest(BaseModel):
    """The exact required metadata set from master §655-676."""

    id: str

    @field_validator("id")
    @classmethod
    def _id_must_be_a_safe_path_segment(cls, value: str) -> str:
        if not _SAFE_ID_PATTERN.match(value) or ".." in value:
            raise ValueError(
                f"id {value!r} must be a safe path segment (letters, digits, '_', '-', '.', '@', "
                "no path separators, no '..')"
            )
        return value

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
