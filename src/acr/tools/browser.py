"""Real browser automation (master §1707-1713), via Playwright.

This is the JS-rendering complement to `acr.tools.web_fetch`'s plain
HTTP GET: `web_fetch` is enough for static pages, but can't see anything a
page's own JavaScript renders. Adding real browser automation was an
explicit, separate user decision from `web_fetch`'s scope-down — Playwright
needs a one-time browser binary download (`playwright install chromium`),
which per project convention is never triggered silently; it's a distinct
action requiring its own explicit confirmation at the moment it happens; see
docs/ARCHITECTURE.md for that record.

Same trust posture as `web_fetch`: rendered page text is untrusted content
(master §1122-1130 — `RETRIEVED_CONTENT` tier) and is scanned for prompt
injection before being returned, never silently blocked.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from acr.security.injection import scan_for_injection
from acr.tools.models import SideEffectLevel, ToolSpec
from acr.tools.web_fetch import _ALLOWED_SCHEMES, InvalidUrlError

_NAVIGATION_TIMEOUT_MS = 15_000


class BrowserNotInstalledError(RuntimeError):
    """Raised when Playwright's browser binary hasn't been installed yet.

    Run `uv run playwright install chromium` to fix this — a one-time
    download, deliberately not triggered automatically by this tool.
    """


async def _browser_fetch_handler(
    session: AsyncSession, url: str, max_chars: int = 4000
) -> dict[str, Any]:
    import httpx
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright

    scheme = httpx.URL(url).scheme
    if scheme not in _ALLOWED_SCHEMES:
        raise InvalidUrlError(f"unsupported URL scheme: {scheme!r}")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page()
                response = await page.goto(url, timeout=_NAVIGATION_TIMEOUT_MS)
                title = await page.title()
                full_text = await page.inner_text("body")
                status_code = response.status if response is not None else 0
            finally:
                await browser.close()
    except PlaywrightError as exc:
        if "Executable doesn't exist" in str(exc):
            raise BrowserNotInstalledError(
                "Playwright's Chromium browser isn't installed — "
                "run `uv run playwright install chromium`"
            ) from exc
        raise

    text = full_text.strip()[:max_chars]
    scan = scan_for_injection(text)
    return {
        "url": url,
        "title": title,
        "status_code": status_code,
        "text": text,
        "truncated": len(full_text.strip()) > max_chars,
        "suspicious": scan.suspicious,
        "matched_patterns": scan.matched_patterns,
    }


BROWSER_FETCH = ToolSpec(
    name="browser_fetch",
    description=(
        "Render a URL in a real (headless) browser and return its visible text, "
        "including JS-rendered content web_fetch can't see."
    ),
    input_schema={"url": "string", "max_chars": "integer"},
    output_schema={"url": "string", "title": "string", "text": "string", "suspicious": "boolean"},
    handler=_browser_fetch_handler,
    permissions=["network.read"],
    side_effect_level=SideEffectLevel.READ_ONLY,
    network_access=True,
    filesystem_access=False,
)
