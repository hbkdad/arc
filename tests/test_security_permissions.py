"""Tests for acr.security.permissions (master §1131-1149)."""

from __future__ import annotations

import pytest

from acr.security.permissions import Capability, PermissionDeniedError, PermissionSet


def test_default_deny_has_nothing_granted() -> None:
    grants = PermissionSet()
    assert grants.has(Capability.MEMORY_READ) is False


def test_has_reflects_explicit_grant() -> None:
    grants = PermissionSet(granted=frozenset({Capability.MEMORY_READ}))
    assert grants.has(Capability.MEMORY_READ) is True
    assert grants.has(Capability.MEMORY_WRITE) is False


def test_has_returns_false_for_unrecognized_capability_string() -> None:
    grants = PermissionSet()
    assert grants.has("not.a.real.capability") is False


def test_require_passes_when_all_granted() -> None:
    grants = PermissionSet(granted=frozenset({Capability.MEMORY_READ, Capability.SKILL_READ}))
    grants.require(Capability.MEMORY_READ, Capability.SKILL_READ)  # no raise


def test_require_raises_on_missing_capability() -> None:
    grants = PermissionSet()
    with pytest.raises(PermissionDeniedError):
        grants.require(Capability.MEMORY_READ)


def test_require_denies_unrecognized_capability_string_instead_of_crashing() -> None:
    grants = PermissionSet(granted=frozenset({Capability.MEMORY_READ}))
    with pytest.raises(PermissionDeniedError):
        grants.require("not.a.real.capability")


def test_require_all_accepts_string_list() -> None:
    grants = PermissionSet(granted=frozenset({Capability.MEMORY_READ}))
    grants.require_all(["memory.read"])  # no raise

    with pytest.raises(PermissionDeniedError):
        grants.require_all(["memory.read", "memory.write"])
