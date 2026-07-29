"""Tests for acr.tools.browser (master §1707-1713, real browser automation).

These skip gracefully when the Playwright Chromium binary isn't installed
(`uv run playwright install chromium`) rather than failing the suite — the
binary download is a deliberate, separate, user-confirmed action (see
docs/ARCHITECTURE.md), not something CI or a fresh checkout can assume.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from acr.tools import browser as browser_module
from acr.tools.browser import BrowserNotInstalledError, _browser_fetch_handler
from acr.tools.web_fetch import InvalidUrlError, UnsafeUrlError


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


async def test_browser_fetch_caps_extraction_before_max_chars_slicing(
    local_html_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Lower the in-page extraction cap far below the fixture page's real
    # body text ("Hello\nlocal test page") to prove the JS-side
    # `.slice()` actually bounds what crosses the CDP protocol, rather
    # than pulling the full body across and truncating in Python
    # afterward.
    # max_chars stays at its default (4000); the fixture page's real body
    # ("Hello\nlocal test page") is well under that, so if the cap weren't
    # actually applied in-page, this would return the full body untouched.
    monkeypatch.setattr(browser_module, "_EXTRACT_CHAR_CAP", 5)

    result = await _fetch_or_skip(local_html_server + "/")

    assert result["text"] == "Hello"


async def test_browser_fetch_raises_for_a_non_http_scheme() -> None:
    with pytest.raises(InvalidUrlError):
        await _browser_fetch_handler(None, "file:///etc/passwd")  # type: ignore[arg-type]


async def test_browser_fetch_refuses_the_cloud_metadata_address() -> None:
    # Same host-safety check as web_fetch, applied before any real
    # Playwright/network activity happens -- a literal IP, so this doesn't
    # touch real DNS/network.
    with pytest.raises(UnsafeUrlError, match=r"169.254.169.254"):
        await _browser_fetch_handler(None, "http://169.254.169.254/latest/meta-data/")  # type: ignore[arg-type]


async def test_browser_fetch_translates_missing_executable_into_a_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale/missing Chromium binary must surface as `BrowserNotInstalledError`
    with the fix-it command, not Playwright's own raw error text -- can't be
    exercised against a real Playwright install (it's already installed on
    dev/CI machines that run this suite), so the failure is simulated."""
    import playwright.async_api as playwright_async_api
    from playwright.async_api import Error as PlaywrightError

    class _FakeChromium:
        async def launch(self) -> None:
            raise PlaywrightError("BrowserType.launch: Executable doesn't exist at /fake/path")

    class _FakePlaywright:
        chromium = _FakeChromium()

    @asynccontextmanager
    async def _fake_async_playwright() -> AsyncIterator[_FakePlaywright]:
        yield _FakePlaywright()

    monkeypatch.setattr(playwright_async_api, "async_playwright", _fake_async_playwright)

    # 127.0.0.1 (not example.invalid): the URL now passes a real host-safety
    # check (`_assert_safe_host`, DNS resolution included) before the fake
    # Playwright ever runs, so it must resolve -- loopback is deliberately
    # not blocked (see UnsafeUrlError's docstring).
    with pytest.raises(BrowserNotInstalledError, match="playwright install chromium"):
        await _browser_fetch_handler(None, "http://127.0.0.1:1/")  # type: ignore[arg-type]


async def test_browser_fetch_reraises_other_playwright_errors_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import playwright.async_api as playwright_async_api
    from playwright.async_api import Error as PlaywrightError

    class _FakeChromium:
        async def launch(self) -> None:
            raise PlaywrightError("some unrelated navigation failure")

    class _FakePlaywright:
        chromium = _FakeChromium()

    @asynccontextmanager
    async def _fake_async_playwright() -> AsyncIterator[_FakePlaywright]:
        yield _FakePlaywright()

    monkeypatch.setattr(playwright_async_api, "async_playwright", _fake_async_playwright)

    with pytest.raises(PlaywrightError, match="unrelated navigation failure"):
        await _browser_fetch_handler(None, "http://127.0.0.1:1/")  # type: ignore[arg-type]
