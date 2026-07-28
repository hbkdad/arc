"""GitHub search tool (master §1707-1713, Phase 13 GitHub integration).

Read-only by design (per explicit user decision): searches issues and pull
requests across GitHub via the `gh` CLI, which is already authenticated on
this machine. No token is ever read, stored, or passed through ACR's own
code — `gh` handles its own credential storage, so nothing GitHub-shaped
touches ACR's memory, logs, or telemetry. Nothing here posts, comments, or
otherwise writes to GitHub; that's a distinct, larger decision (master's
own "Publishing... requires explicit permission" boundary) this tool
deliberately doesn't cross.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from acr.security.injection import scan_for_injection
from acr.tools.models import SideEffectLevel, ToolSpec


class GhCliNotFoundError(RuntimeError):
    """Raised when the `gh` binary isn't on PATH."""


class GhCliError(RuntimeError):
    """Raised when `gh api` exits non-zero (bad query, not authenticated, etc.)."""


class GhCliTimeoutError(RuntimeError):
    """Raised when `gh api` doesn't return within the timeout — never hang the caller."""


_TIMEOUT_SECONDS = 15.0


async def _run_gh_api(endpoint: str) -> dict[str, Any]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "gh",
            "api",
            endpoint,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise GhCliNotFoundError("the 'gh' CLI is not installed or not on PATH") from exc

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise GhCliTimeoutError(f"gh api did not respond within {_TIMEOUT_SECONDS}s") from exc

    if proc.returncode != 0:
        raise GhCliError(stderr.decode(errors="replace").strip() or "gh api failed")
    return json.loads(stdout)


async def _github_search_handler(
    session: AsyncSession, query: str, limit: int = 5
) -> list[dict[str, Any]]:
    endpoint = f"search/issues?q={quote(query, safe='')}&per_page={limit}"
    body = await _run_gh_api(endpoint)
    results = []
    for item in body.get("items", [])[:limit]:
        repo_url = item.get("repository_url", "")
        title = item.get("title") or ""
        scan = scan_for_injection(title)
        results.append(
            {
                "repository": repo_url.rsplit("/repos/", 1)[-1] if repo_url else "",
                "number": item.get("number"),
                "title": title,
                "state": item.get("state"),
                "is_pull_request": "pull_request" in item,
                "url": item.get("html_url"),
                "comments": item.get("comments"),
                "created_at": item.get("created_at"),
                "suspicious": scan.suspicious,
            }
        )
    return results


GITHUB_SEARCH = ToolSpec(
    name="github_search",
    description="Search GitHub issues and pull requests (read-only, via the gh CLI).",
    input_schema={"query": "string", "limit": "integer"},
    output_schema={"results": "array"},
    handler=_github_search_handler,
    permissions=["network.read"],
    side_effect_level=SideEffectLevel.READ_ONLY,
    network_access=True,
    filesystem_access=False,
)
