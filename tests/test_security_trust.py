"""Tests for acr.security.trust (master §1118-1130)."""

from __future__ import annotations

import pytest

from acr.memory.models import MemoryRecord, MemoryScope, MemoryStatus, MemoryType
from acr.security.trust import TrustLevel, combine_trust, memory_trust_level


def _record(status: MemoryStatus) -> MemoryRecord:
    return MemoryRecord(
        type=MemoryType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        subject="test",
        content="test content",
        source_type="test",
        status=status,
    )


def test_combine_trust_takes_the_minimum() -> None:
    result = combine_trust(
        TrustLevel.CORE_POLICY, TrustLevel.UNTRUSTED, TrustLevel.USER_INSTRUCTION
    )
    assert result is TrustLevel.UNTRUSTED


def test_combine_trust_of_a_single_level_is_itself() -> None:
    assert combine_trust(TrustLevel.SIGNED_SKILL) is TrustLevel.SIGNED_SKILL


def test_combine_trust_requires_at_least_one_level() -> None:
    with pytest.raises(ValueError, match="at least one level"):
        combine_trust()


def test_confirmed_memory_is_verified() -> None:
    assert memory_trust_level(_record(MemoryStatus.CONFIRMED)) is TrustLevel.VERIFIED_MEMORY


def test_quarantined_memory_is_untrusted() -> None:
    assert memory_trust_level(_record(MemoryStatus.QUARANTINED)) is TrustLevel.UNTRUSTED


@pytest.mark.parametrize(
    "status", [MemoryStatus.CANDIDATE, MemoryStatus.SUPERSEDED, MemoryStatus.ARCHIVED]
)
def test_other_statuses_are_retrieved_content(status: MemoryStatus) -> None:
    assert memory_trust_level(_record(status)) is TrustLevel.RETRIEVED_CONTENT
