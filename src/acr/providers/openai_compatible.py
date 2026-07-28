"""OpenAI-compatible chat-completions provider (master §894-895, §133-139).

Works with anything speaking the OpenAI `/v1/chat/completions` wire format —
OpenAI itself, or a compatible self-hosted/third-party endpoint. Requires an
explicit API key: `is_available()` returns False without ever making a
network call if none is configured (master §41 — no secret is ever required
by this repo; a key must come from `ACR_OPENAI_API_KEY`, never hardcoded).
"""

from __future__ import annotations

import httpx

from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
_TIMEOUT_SECONDS = 60.0


class OpenAICompatibleProvider(ModelProvider):
    name = "openai_compatible"

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
            raise RuntimeError("OpenAICompatibleProvider requires an API key")

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": request.prompt}],
                    "max_tokens": request.max_output_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()

        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return CompletionResult(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )
