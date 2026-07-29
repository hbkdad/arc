"""Shared SQLite FTS5 query building.

A bare-word FTS5 `MATCH` query ANDs every term by default, so passing a full
natural-language string straight through would only match content containing
*every single word* of it. This builds an OR-joined, quoted,
stopword-filtered query instead. Quoting each token also escapes FTS5
query-syntax metacharacters a raw sentence could otherwise trip over (e.g. a
colon or leading hyphen). Shared by memory retrieval and skill search so
free-text queries behave the same way everywhere in ACR.
"""

from __future__ import annotations

import re

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")

# Common English function words — left in, an OR-joined query would treat
# every one of them as an independent match signal, making nearly any query
# match nearly any content.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "in",
        "on",
        "at",
        "to",
        "of",
        "and",
        "or",
        "for",
        "with",
        "without",
        "it",
        "its",
        "as",
        "by",
        "from",
        "but",
        "not",
        "no",
        "nor",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "them",
        "their",
        "his",
        "her",
        "our",
        "your",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "will",
        "would",
        "can",
        "could",
        "should",
        "shall",
        "may",
        "might",
        "must",
    ]
)


def tokenize(text: str) -> list[str]:
    """Stopword-filtered word tokens (original casing preserved) — the
    shared vocabulary every keyword-relevance comparison in ACR (FTS
    search, tool exposure) builds on, so "does this text meaningfully
    overlap with that text" means the same thing everywhere."""
    return [t for t in _TOKEN_PATTERN.findall(text) if t.lower() not in _STOPWORDS]


def build_match_query(query: str) -> str:
    """Build a safe, OR-joined FTS5 MATCH query. Empty for an all-stopword input."""
    return " OR ".join(f'"{token}"' for token in tokenize(query))


def bm25_to_relevance(rank: float) -> float:
    """Map SQLite FTS5's `bm25()` output to a bounded (0, 1) relevance score.

    `bm25()` is <=0 with *more negative meaning a better match*, and its
    magnitude grows with corpus size and term frequency — unlike a distance
    metric starting at 0, there's no fixed scale to invert with `1/(1+rank)`.
    (`1/(1+rank)` was tried here first and silently went negative once a
    match's `rank` passed -1, which happens routinely once a table holds a
    few hundred rows — worth remembering if this function's shape ever looks
    like it needs "simplifying" back to that.) Flipping the sign first keeps
    this monotonic and bounded regardless of corpus size.
    """
    strength = -rank
    return max(0.0, strength / (1.0 + strength))
