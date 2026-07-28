"""Tests for the shared token estimator (acr.core.tokens)."""

from __future__ import annotations

from acr.core.tokens import estimate_tokens
from acr.memory.retrieval import estimate_tokens as memory_estimate_tokens


def test_estimate_tokens_is_roughly_length_over_four() -> None:
    assert estimate_tokens("a" * 40) == 10


def test_estimate_tokens_never_returns_zero() -> None:
    assert estimate_tokens("") == 1


def test_memory_retrieval_reexports_the_same_function() -> None:
    assert memory_estimate_tokens is estimate_tokens
