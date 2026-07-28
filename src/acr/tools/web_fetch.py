"""Web fetch tool (master §1707-1713's "browser automation," scoped to a
plain HTTP GET + text extraction — see docs/ARCHITECTURE.md for why this
isn't a real browser: Playwright needs to download a ~100-300MB browser
binary on first use, which is a real action requiring explicit sign-off,
not something to trigger silently. `httpx` is already a dependency, so
this needs nothing new to install.

Fetched content is untrusted (master §1122-1130's trust boundary — it's
`RETRIEVED_CONTENT` at best, same tier as retrieved memory) and is scanned
for prompt injection before being returned, never blocked outright — the
caller decides what to do with a `suspicious` result, same as every other
`scan_for_injection()` call site.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from acr.security.injection import scan_for_injection
from acr.tools.models import SideEffectLevel, ToolSpec

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_SKIP_TAGS = frozenset({"script", "style", "head"})
_WHITESPACE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    """Collects visible text, dropping script/style content and markup."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return _WHITESPACE.sub(" ", " ".join(self._chunks)).strip()


def extract_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


class InvalidUrlError(ValueError):
    """Raised for a URL scheme other than http(s) — no file://, data://, etc."""


async def _web_fetch_handler(
    session: AsyncSession, url: str, max_chars: int = 4000
) -> dict[str, Any]:
    scheme = httpx.URL(url).scheme
    if scheme not in _ALLOWED_SCHEMES:
        raise InvalidUrlError(f"unsupported URL scheme: {scheme!r}")

    async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()

    full_text = extract_text(response.text)
    text = full_text[:max_chars]
    scan = scan_for_injection(text)
    return {
        "url": str(response.url),
        "status_code": response.status_code,
        "text": text,
        "truncated": len(full_text) > max_chars,
        "suspicious": scan.suspicious,
        "matched_patterns": scan.matched_patterns,
    }


WEB_FETCH = ToolSpec(
    name="web_fetch",
    description="Fetch a URL over HTTP(S) and return its extracted text (no JS rendering).",
    input_schema={"url": "string", "max_chars": "integer"},
    output_schema={"url": "string", "text": "string", "suspicious": "boolean"},
    handler=_web_fetch_handler,
    permissions=["network.read"],
    side_effect_level=SideEffectLevel.READ_ONLY,
    network_access=True,
    filesystem_access=False,
)
