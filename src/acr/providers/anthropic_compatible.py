"""Anthropic-compatible messages provider (master §894-895, §133-139).

Speaks the Anthropic `/v1/messages` wire format. Requires an explicit API
key: `is_available()` returns False without ever making a network call if
none is configured (master §41 — a key must come from
`ACR_ANTHROPIC_API_KEY`, never hardcoded).
"""

from __future__ import annotations

import httpx

from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_API_VERSION = "2023-06-01"
_TIMEOUT_SECONDS = 60.0


class AnthropicCompatibleProvider(ModelProvider):
    name = "anthropic_compatible"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def is_available(self) -> bool:
        return bool(self.api_key)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if not self.api_key:
            raise RuntimeError("AnthropicCompatibleProvider requires an API key")

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": DEFAULT_API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": request.max_output_tokens,
                    "messages": [{"role": "user", "content": request.prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()

        text = "".join(block.get("text", "") for block in data.get("content", []))
        usage = data.get("usage", {})
        return CompletionResult(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )
