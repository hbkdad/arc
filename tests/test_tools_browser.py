"""Tests for acr.tools.browser (master §1707-1713, real browser automation).

These skip gracefully when the Playwright Chromium binary isn't installed
(`uv run playwright install chromium`) rather than failing the suite — the
binary download is a deliberate, separate, user-confirmed action (see
docs/ARCHITECTURE.md), not something CI or a fresh checkout can assume.
"""

from __future__ import annotations

import pytest

from acr.tools.browser import BrowserNotInstalledError, _browser_fetch_handler
from acr.tools.web_fetch import InvalidUrlError


async def _fetch_or_skip(url: str, **kwargs: object) -> dict:
    try:
        return await _browser_fetch_handler(None, url, **kwargs)  # type: ignore[arg-type]
    except BrowserNotInstalledError:
        pytest.skip("Playwright Chromium not installed — run `playwright install chromium`")


async def test_browser_fetch_renders_real_content(local_html_server: str) -> None:
    result = await _fetch_or_skip(local_html_server + "/")

    assert "Hello" in result["text"]
    assert result["status_code"] == 200
    assert result["suspicious"] is False


async def test_browser_fetch_truncates_to_max_chars(local_html_server: str) -> None:
    result = await _fetch_or_skip(local_html_server + "/", max_chars=3)

    assert len(result["text"]) == 3
    assert result["truncated"] is True


async def test_browser_fetch_raises_for_a_non_http_scheme() -> None:
    with pytest.raises(InvalidUrlError):
        await _browser_fetch_handler(None, "file:///etc/passwd")  # type: ignore[arg-type]
