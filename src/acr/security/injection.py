"""Prompt-injection detection (master §1150-1166).

A deterministic v1 heuristic scanner over untrusted content (retrieved
memory, web/document content, tool output) — same "start simple, no LLM
required" reasoning as `acr.memory.retrieval`'s FTS ranking. This flags
content for review; it never silently blocks or silently trusts. False
positives are expected and acceptable — false negatives are the risk this
guards against, so the pattern list errs toward recall over precision.

Detected content must never automatically create memory, activate skills,
create agents, change permissions, execute shell commands, or access
credentials (master §1160-1166) — this module only detects; enforcing that
boundary is the caller's job (e.g. the write controller requiring evidence,
`acr.security.safe_mode` gating activation).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Deliberately broad, case-insensitive phrase patterns for instruction-like
# text embedded in what should be inert data. Each is a plain phrase, not
# meant to be exhaustive — a real deployment would tune/extend this list
# against observed attempts, not treat it as complete.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore-previous-instructions",
        re.compile(r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+instructions", re.I),
    ),
    ("disregard-instructions", re.compile(r"disregard\s+(the\s+)?(system|previous)\s", re.I)),
    ("new-instructions", re.compile(r"\b(your\s+)?new\s+instructions?\s+(are|is)\b", re.I)),
    ("act-as", re.compile(r"\byou\s+(must\s+)?now\s+act\s+as\b", re.I)),
    ("system-prompt-override", re.compile(r"\bsystem\s*:\s*", re.I)),
    ("reveal-prompt", re.compile(r"\breveal\s+(your\s+)?(system\s+)?prompt\b", re.I)),
    (
        "exfiltrate-credentials",
        re.compile(r"\b(send|post|email)\s+.{0,30}(api[_ -]?key|password|secret|token)\b", re.I),
    ),
    ("grant-permission", re.compile(r"\bgrant\s+(yourself\s+|it\s+)?(permission|access)\b", re.I)),
]


@dataclass(frozen=True, slots=True)
class InjectionScanResult:
    suspicious: bool
    matched_patterns: list[str] = field(default_factory=list)


def scan_for_injection(text: str) -> InjectionScanResult:
    matched = [name for name, pattern in _PATTERNS if pattern.search(text)]
    return InjectionScanResult(suspicious=bool(matched), matched_patterns=matched)
