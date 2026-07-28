"""Tests for acr.security.safe_mode (master §1534-1550)."""

from __future__ import annotations

import pytest

from acr.security.safe_mode import SafeModeError, require_not_safe_mode


def test_allows_when_safe_mode_is_off() -> None:
    require_not_safe_mode(False, "some.operation")  # no raise


def test_blocks_when_safe_mode_is_on() -> None:
    with pytest.raises(SafeModeError, match=r"some\.operation"):
        require_not_safe_mode(True, "some.operation")
