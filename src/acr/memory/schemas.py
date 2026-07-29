"""Structured payloads for memory types master's spec gives specific fields
to (§615-629 failure memory; a decision record shape informed by standard
architecture-decision-record practice) -- carried in
`MemoryRecord.structured_payload` (a generic JSON column on the one unified
memory table, per `acr.memory.models`'s own docstring) rather than a
bespoke table per type, but not left as an unstructured free-form dict
either. Parsing is best-effort and never raises: `structured_payload`
predates this schema, and some records (or a future memory type) legitimately
won't match it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FailurePayload:
    """Master §615-629: task class, symptom, and (once known) root cause
    and resolution -- the fields a future similar failure needs to be
    recognized and, ideally, avoided."""

    task_class: str
    symptom: str
    root_cause: str | None = None
    resolution: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True, slots=True)
class DecisionPayload:
    """An architecture/operational decision record: what was decided, what
    else was considered, why, and what it implies -- the standard ADR
    shape, so a DECISION memory is queryable structure, not just prose."""

    context: str
    alternatives: list[str] = field(default_factory=list)
    rationale: str = ""
    consequences: str = ""
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_failure_payload(payload: dict[str, Any]) -> FailurePayload | None:
    """Returns `None` (never raises) for a payload missing the required
    fields -- a legacy or free-form `structured_payload` predating this
    schema, not a bug."""
    try:
        return FailurePayload(
            task_class=payload["task_class"],
            symptom=payload["symptom"],
            root_cause=payload.get("root_cause"),
            resolution=payload.get("resolution"),
        )
    except (KeyError, TypeError):
        return None


def parse_decision_payload(payload: dict[str, Any]) -> DecisionPayload | None:
    """Returns `None` (never raises) for a payload missing `context`."""
    try:
        return DecisionPayload(
            context=payload["context"],
            alternatives=list(payload.get("alternatives", [])),
            rationale=payload.get("rationale", ""),
            consequences=payload.get("consequences", ""),
            assumptions=list(payload.get("assumptions", [])),
        )
    except (KeyError, TypeError):
        return None
