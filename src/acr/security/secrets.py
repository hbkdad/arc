"""Secret redaction (master §1181-1191).

"Never store secrets in memory, telemetry, skills, prompts, Git, screenshots,
public logs... Redact common secret formats." This is a deterministic
pattern-based redactor — it cannot catch every possible secret shape, but it
catches the common, recognizable ones before they reach a log or a DB row.
Wired into `acr.telemetry.recorder.TelemetryRecorder` so every persisted
event payload passes through it.
"""

from __future__ import annotations

import re

_REDACTED = "[REDACTED]"

# (name, pattern) — recognizable secret formats. Order matters only for
# readability; each pattern is applied independently.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_api_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("anthropic_api_key", re.compile(r"sk-ant-[A-Za-z0-9-]{20,}")),
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("bearer_token", re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{10,}")),
    (
        "generic_api_key_assignment",
        re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+]{12,}['\"]?"),
    ),
    (
        "pem_private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    ),
]


def redact_secrets(text: str) -> str:
    redacted = text
    for _name, pattern in _PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return redacted


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) for _name, pattern in _PATTERNS)


def redact_mapping(payload: dict[str, object]) -> dict[str, object]:
    """Recursively redact string values in a JSON-like dict (telemetry payloads)."""
    result: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            result[key] = redact_secrets(value)
        elif isinstance(value, dict):
            result[key] = redact_mapping(value)
        elif isinstance(value, list):
            result[key] = [
                redact_secrets(item)
                if isinstance(item, str)
                else (redact_mapping(item) if isinstance(item, dict) else item)
                for item in value
            ]
        else:
            result[key] = value
    return result
