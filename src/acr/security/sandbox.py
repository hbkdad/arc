"""Sandbox policy (master §1168-1180).

ACR has no code/skill execution engine yet (skills are metadata + human-
readable instructions, not executable code — see Phase 4/9), so a full
process-isolation sandbox (containers, seccomp, etc.) would be
infrastructure with nothing to isolate yet. What's genuinely usable today:
a validated `SandboxPolicy` and a real, testable environment-variable
filter — the "no host credentials" and "environment filtering" requirements
— ready for whatever executes untrusted code first (Phase 9 skill
validation, or a future shell tool).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acr.security.secrets import redact_secrets

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_ENV_ALLOWLIST = frozenset({"PATH", "LANG", "LC_ALL", "TZ"})


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """master §1170-1179's requirements, as a validated config object."""

    restrict_filesystem: bool = True
    temporary_workspace: bool = True
    network_disabled: bool = True
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_output_bytes: int = 1_000_000
    env_allowlist: frozenset[str] = field(default_factory=lambda: DEFAULT_ENV_ALLOWLIST)
    audit_logging: bool = True


def build_sandboxed_env(policy: SandboxPolicy, base_env: dict[str, str]) -> dict[str, str]:
    """Filter `base_env` down to `policy.env_allowlist`, then redact any
    value that still looks like a secret (defense in depth — an allowlisted
    variable like PATH should never contain one, but never trust that)."""
    return {
        key: redact_secrets(value) for key, value in base_env.items() if key in policy.env_allowlist
    }
