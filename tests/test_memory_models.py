"""Tests for acr.memory.models.MemoryRecord derived properties."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from acr.memory.models import MemoryRecord, MemoryScope, MemoryStatus, MemoryType


def _record(**overrides: object) -> MemoryRecord:
    defaults: dict[str, object] = dict(
        type=MemoryType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        subject="acr.test",
        content="test content",
        source_type="test",
        status=MemoryStatus.CONFIRMED,
    )
    defaults.update(overrides)
    return MemoryRecord(**defaults)  # type: ignore[arg-type]


def test_is_current_true_for_confirmed_with_no_expiry() -> None:
    assert _record().is_current is True


def test_is_current_false_once_superseded() -> None:
    assert _record(status=MemoryStatus.SUPERSEDED).is_current is False


def test_is_current_false_once_valid_until_has_passed() -> None:
    expired = _record(valid_until=datetime.now(UTC) - timedelta(days=1))
    assert expired.is_current is False


def test_is_current_true_when_valid_until_is_in_the_future() -> None:
    still_valid = _record(valid_until=datetime.now(UTC) + timedelta(days=1))
    assert still_valid.is_current is True
