"""Tests for acr.memory.schemas and the remember_failure/remember_decision
write-controller helpers built on top of them."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory import (
    DecisionPayload,
    FailurePayload,
    MemoryStatus,
    MemoryType,
    parse_decision_payload,
    parse_failure_payload,
)
from acr.memory.write_controller import remember_decision, remember_failure


def test_failure_payload_to_dict_omits_unset_optional_fields() -> None:
    payload = FailurePayload(task_class="ui-audit", symptom="dead CSS class")

    assert payload.to_dict() == {"task_class": "ui-audit", "symptom": "dead CSS class"}


def test_failure_payload_to_dict_includes_set_optional_fields() -> None:
    payload = FailurePayload(
        task_class="ui-audit",
        symptom="dead CSS class",
        root_cause="JS-set className with no matching CSS rule",
        resolution="added the missing rule",
    )

    d = payload.to_dict()
    assert d["root_cause"] == "JS-set className with no matching CSS rule"
    assert d["resolution"] == "added the missing rule"


def test_parse_failure_payload_round_trips() -> None:
    payload = FailurePayload(task_class="ui-audit", symptom="dead CSS class")

    parsed = parse_failure_payload(payload.to_dict())

    assert parsed == payload


def test_parse_failure_payload_returns_none_for_a_payload_missing_required_fields() -> None:
    assert parse_failure_payload({"symptom": "no task_class here"}) is None
    assert parse_failure_payload({}) is None


def test_parse_decision_payload_round_trips() -> None:
    payload = DecisionPayload(
        context="which dashboard theme to ship",
        alternatives=["replace the default theme", "add a toggle"],
        rationale="a toggle keeps the existing theme intact",
        consequences="two themes to keep in sync going forward",
        assumptions=["users can find the toggle"],
    )

    parsed = parse_decision_payload(payload.to_dict())

    assert parsed == payload


def test_parse_decision_payload_returns_none_for_a_payload_missing_context() -> None:
    assert parse_decision_payload({"rationale": "no context field here"}) is None


async def test_remember_failure_writes_the_symptom_as_content(db_session: AsyncSession) -> None:
    payload = FailurePayload(task_class="ui-audit", symptom="dead status-fail CSS class")

    _evaluation, record = await remember_failure(
        db_session,
        payload,
        subject="acr.dashboard.status_indicator",
        source_type="session",
        evidence="observed directly in base.html",
    )

    assert record is not None
    assert record.type is MemoryType.FAILURE
    assert record.content == "dead status-fail CSS class"
    assert record.structured_payload == payload.to_dict()
    # confidence=0.7 (the default) is below MIN_CONFIDENCE_FOR_CONFIRMED
    # (0.75) -- CANDIDATE, not CONFIRMED, is the correct outcome here.
    assert record.status is MemoryStatus.CANDIDATE


async def test_remember_decision_writes_the_rationale_as_content(db_session: AsyncSession) -> None:
    payload = DecisionPayload(
        context="how to add a second dashboard theme",
        alternatives=["replace the default", "add a toggle"],
        rationale="a toggle keeps the existing theme intact",
    )

    _evaluation, record = await remember_decision(
        db_session,
        payload,
        subject="acr.dashboard.theme_toggle",
        source_type="session",
        evidence="observed directly",
    )

    assert record is not None
    assert record.type is MemoryType.DECISION
    assert record.content == "a toggle keeps the existing theme intact"
    assert record.structured_payload == payload.to_dict()


async def test_remember_decision_falls_back_to_context_when_rationale_is_empty(
    db_session: AsyncSession,
) -> None:
    payload = DecisionPayload(context="no rationale given yet")

    _evaluation, record = await remember_decision(
        db_session,
        payload,
        subject="acr.dashboard.theme_toggle",
        source_type="session",
        evidence="observed directly",
    )

    assert record is not None
    assert record.content == "no rationale given yet"
