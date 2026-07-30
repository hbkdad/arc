"""Tests for the shared token estimator (acr.core.tokens)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from acr.core.tokens import estimate_tokens
from acr.memory.retrieval import estimate_tokens as memory_estimate_tokens


def test_estimate_tokens_is_roughly_length_over_four() -> None:
    assert estimate_tokens("a" * 40) == 10


def test_estimate_tokens_never_returns_zero() -> None:
    assert estimate_tokens("") == 1


def test_memory_retrieval_reexports_the_same_function() -> None:
    assert memory_estimate_tokens is estimate_tokens


@given(st.text())
def test_estimate_tokens_is_always_a_positive_integer(value: str) -> None:
    """Every caller (the context compiler's budget math, memory retrieval's
    relevance scoring) treats this as a strictly positive weight -- a
    stray 0 would make something free to include in a budget it should
    count against; a negative value isn't meaningful at all. Checked
    across arbitrary text (including empty strings and Unicode a
    hand-picked example wouldn't cover), not just the ASCII example
    above."""
    tokens = estimate_tokens(value)
    assert isinstance(tokens, int)
    assert tokens >= 1


@given(st.text(), st.text())
def test_estimate_tokens_is_monotonic_in_length(a: str, b: str) -> None:
    """A real invariant this shared estimator must hold for every caller
    that reasons about it changing as text grows or shrinks (the context
    compiler trimming toward a budget, in particular): a text that is no
    longer than another must never estimate to *more* tokens."""
    if len(a) <= len(b):
        assert estimate_tokens(a) <= estimate_tokens(b)
