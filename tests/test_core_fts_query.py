"""Tests for the shared FTS5 query builder (acr.core.fts_query)."""

from __future__ import annotations

from acr.core.fts_query import bm25_to_relevance, build_match_query


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
