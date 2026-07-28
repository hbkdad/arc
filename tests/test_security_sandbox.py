"""Tests for acr.security.sandbox (master §1168-1180)."""

from __future__ import annotations

from acr.security.sandbox import SandboxPolicy, build_sandboxed_env


def test_default_policy_is_restrictive() -> None:
    policy = SandboxPolicy()
    assert policy.restrict_filesystem is True
    assert policy.network_disabled is True
    assert policy.temporary_workspace is True


def test_build_sandboxed_env_drops_non_allowlisted_vars() -> None:
    policy = SandboxPolicy(env_allowlist=frozenset({"PATH"}))
    env = build_sandboxed_env(policy, {"PATH": "/usr/bin", "SECRET_TOKEN": "sk-shouldnotleak12345"})
    assert env == {"PATH": "/usr/bin"}


def test_build_sandboxed_env_redacts_secret_looking_allowlisted_values() -> None:
    policy = SandboxPolicy(env_allowlist=frozenset({"PATH"}))
    env = build_sandboxed_env(policy, {"PATH": "sk-abcdefghijklmnopqrstuvwxyz012345"})
    assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in env["PATH"]


def test_build_sandboxed_env_with_empty_base_env() -> None:
    assert build_sandboxed_env(SandboxPolicy(), {}) == {}
