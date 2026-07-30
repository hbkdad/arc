"""Tests for the shared FTS5 query builder (acr.core.fts_query)."""

from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from acr.core.fts_query import bm25_to_relevance, build_match_query, tokenize


def test_build_match_query_ors_content_words_and_drops_stopwords() -> None:
    assert build_match_query("Explain the SQLite storage layer") == (
        '"Explain" OR "SQLite" OR "storage" OR "layer"'
    )


def test_build_match_query_is_empty_for_stopwords_only() -> None:
    assert build_match_query("the a an") == ""


def test_build_match_query_is_empty_for_blank_input() -> None:
    assert build_match_query("   ") == ""


def test_bm25_to_relevance_stays_positive_past_the_naive_formula_breaking_point() -> None:
    # SQLite's real bm25() output is <=0 and grows more negative (not more
    # positive) as a match gets stronger and/or the corpus grows -- a naive
    # `1.0 / (1.0 + rank)` goes negative once rank < -1, which happens
    # routinely once a table holds a few hundred rows. -15.7 is a real
    # observed bm25() value from a ~500-row FTS5 table.
    assert bm25_to_relevance(-15.7) > 0.9


def test_bm25_to_relevance_is_monotonically_increasing_with_match_strength() -> None:
    weak = bm25_to_relevance(-0.000002)
    medium = bm25_to_relevance(-2.0)
    strong = bm25_to_relevance(-15.7)

    assert 0.0 < weak < medium < strong < 1.0


def test_bm25_to_relevance_never_goes_negative() -> None:
    assert bm25_to_relevance(0.0) == 0.0
    assert bm25_to_relevance(-1000.0) > 0.0


def test_bm25_to_relevance_rejects_a_positive_rank_instead_of_dividing_by_zero() -> None:
    # A caller passing rank=1.0 violates bm25()'s own <=0 contract -- found
    # by a Hypothesis property test below, not a real caller (both real
    # call sites pass an actual bm25() result straight through). Locked in
    # as a plain example once found: this exact input used to raise
    # ZeroDivisionError (1.0 + -1.0 == 0.0 in the denominator).
    assert bm25_to_relevance(1.0) == 0.0


def test_bm25_to_relevance_rejects_a_rank_that_would_exceed_the_documented_bound() -> None:
    # rank=1.5 used to return 3.0 -- outside the (0, 1) bound this
    # function's own docstring promises, and silently so (no crash, no
    # error, just a wrong number a caller would have no reason to
    # suspect).
    assert bm25_to_relevance(1.5) == 0.0


def test_bm25_to_relevance_clamps_an_astronomically_large_magnitude_rank() -> None:
    # Also found by the property test below: floating-point precision loss
    # (1.0 + strength rounds to the same float as strength once strength
    # exceeds ~1e16) made this land on exactly 1.0 -- outside the
    # documented open interval, even though no real bm25() corpus would
    # ever produce a magnitude anywhere near this.
    assert bm25_to_relevance(-9_942_258_759_215_308.0) < 1.0


@given(st.floats(allow_nan=False))
def test_bm25_to_relevance_is_always_bounded_and_never_crashes(rank: float) -> None:
    """Property, not example: for *any* real rank a caller could pass --
    not just the ones a human thought to write down -- this must return a
    finite value in [0, 1) and never raise. This is exactly the class of
    bug (a boundary value that divides by zero, a range the code silently
    exceeds) property-based testing is suited to find versus example-based
    tests, which only ever check the specific inputs someone thought of."""
    relevance = bm25_to_relevance(rank)
    assert math.isfinite(relevance)
    assert 0.0 <= relevance < 1.0


@given(st.text())
def test_tokenize_never_produces_a_token_containing_a_quote_character(text: str) -> None:
    """Safety property, not example: `build_match_query()` wraps every
    token in literal double-quotes with no escaping of its own, so this is
    the actual invariant that makes that safe -- every token tokenize()
    produces must itself be free of the character it's about to be
    wrapped in. Checked across arbitrary Unicode input (including
    adversarial strings a human wouldn't think to hand-write), not just
    the plain-English example above."""
    for token in tokenize(text):
        assert '"' not in token


@given(st.text())
def test_build_match_query_output_has_balanced_quotes(text: str) -> None:
    """For any input, the built query must be safe to embed in a MATCH
    clause: an even number of double-quote characters (every token
    opened is also closed), never an odd, dangling one that would leave
    the rest of the query text unexpectedly inside a quoted string."""
    query = build_match_query(text)
    assert query.count('"') % 2 == 0
