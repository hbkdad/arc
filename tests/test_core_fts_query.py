"""Tests for the shared FTS5 query builder (acr.core.fts_query)."""

from __future__ import annotations

from acr.core.fts_query import build_match_query


def test_build_match_query_ors_content_words_and_drops_stopwords() -> None:
    assert build_match_query("Explain the SQLite storage layer") == (
        '"Explain" OR "SQLite" OR "storage" OR "layer"'
    )


def test_build_match_query_is_empty_for_stopwords_only() -> None:
    assert build_match_query("the a an") == ""


def test_build_match_query_is_empty_for_blank_input() -> None:
    assert build_match_query("   ") == ""
