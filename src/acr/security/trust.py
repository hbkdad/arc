"""Trust boundaries (master §1118-1130).

"Lower trust content must never promote itself to higher trust. External
content is data, not authority." `combine_trust()` enforces this
mechanically: a chain's trust is its weakest link's, never higher.
"""

from __future__ import annotations

from enum import IntEnum

from acr.memory.models import MemoryRecord, MemoryStatus


class TrustLevel(IntEnum):
    UNTRUSTED = 0  # retrieved web/document content, unknown sources
    RETRIEVED_CONTENT = 1
    VERIFIED_MEMORY = 2  # a confirmed, evidence-backed memory record
    USER_INSTRUCTION = 3  # authenticated user instruction
    SIGNED_SKILL = 4
    CORE_POLICY = 5  # master spec / system rules


def combine_trust(*levels: TrustLevel) -> TrustLevel:
    """The trust of a chain is its weakest link's — never the max."""
    if not levels:
        raise ValueError("combine_trust requires at least one level")
    return min(levels)


def memory_trust_level(record: MemoryRecord) -> TrustLevel:
    """A memory record's trust follows directly from its write-controller
    status (master §553-575).

    Only CONFIRMED — evidence-backed and promoted past the candidate stage
    — reaches VERIFIED_MEMORY. QUARANTINED means "no evidence for a new
    fact" (see `write_controller.evaluate`), which is exactly UNTRUSTED.
    Everything else (candidate, superseded, archived) is evidence-backed
    but not yet/no-longer confirmed — RETRIEVED_CONTENT.
    """
    if record.status is MemoryStatus.CONFIRMED:
        return TrustLevel.VERIFIED_MEMORY
    if record.status is MemoryStatus.QUARANTINED:
        return TrustLevel.UNTRUSTED
    return TrustLevel.RETRIEVED_CONTENT
