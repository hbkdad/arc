"""Shared token-cost estimation (master §7-8, §325-381).

A rough character-based estimate, not a real tokenizer — swap this out for a
model-specific tokenizer if/when one is worth depending on. Shared by memory
retrieval and the context compiler so the two never disagree about what a
"token" costs.
"""

from __future__ import annotations

_CHARS_PER_TOKEN = 4


def estimate_tokens(value: str) -> int:
    return max(1, len(value) // _CHARS_PER_TOKEN)
