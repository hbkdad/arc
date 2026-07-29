"""Ollama local-model provider (master §814-824, §889-892).

Talks only to a local Ollama daemon. Never contacts anything off localhost by
default, so it never needs a credential and never sends data externally.
"""

from __future__ import annotations

import httpx

from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider

DEFAULT_BASE_URL = "http://localhost:11434"
# Not just network latency to a local daemon (which should be near-
# instant) -- measured on Windows, a *fresh process's first* httpx
# request can itself take 1.2-7.2s of cold-start overhead (socket/AV
# interception, asyncio proactor setup) before any bytes cross the wire,
# confirmed by comparing against `curl` (instant) and a warmed-up client
# in the same process (also fast). 1.0s was tight enough to make
# is_available() report a real, running Ollama daemon as unreachable.
_AVAILABILITY_TIMEOUT_SECONDS = 5.0
# Measured directly against a real, already-warm (2.2s load) local model on
# unaccelerated (CPU-only) hardware: ~10 seconds per generated token. At the
# default max_output_tokens=512, 60s wasn't enough to produce even 6 tokens
# -- meaning close to *every* real completion request would fail via
# timeout on exactly the hardware profile ("run it on your own machine, no
# GPU required") this local-first tool is built around. Generous rather
# than tight: a genuinely hung/broken daemon should still time out
# eventually, but shouldn't be confused with "just slow".
_COMPLETION_TIMEOUT_SECONDS = 300.0


class OllamaNoModelError(RuntimeError):
    """Raised when no model is configured and none are pulled locally either."""


class OllamaProvider(ModelProvider):
    name = "ollama"

    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str | None = None) -> None:
        self.base_url = base_url
        # `None` means "auto-detect": Ollama ships with no default model, and
        # every user pulls whatever they want, so hardcoding one name (e.g.
        # "llama3.2") would 404 against any install that doesn't happen to
        # have exactly that pulled — a real bug this phase's own end-to-end
        # smoke test found. Resolved lazily in complete(), not the
        # constructor, so building a provider never does network I/O.
        self.model = model

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=_AVAILABILITY_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == httpx.codes.OK
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        """Local model detection (master §814-824). Empty if the daemon is
        unreachable — never raises."""
        try:
            async with httpx.AsyncClient(timeout=_AVAILABILITY_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError:
            return []
        return [model["name"] for model in data.get("models", [])]

    async def _resolve_model(self) -> str:
        if self.model is not None:
            return self.model
        models = await self.list_models()
        if not models:
            raise OllamaNoModelError(
                "no Ollama model configured (ACR_OLLAMA_MODEL) and none found locally — "
                "pull one first, e.g. `ollama pull llama3.2`"
            )
        return models[0]

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        model = await self._resolve_model()
        async with httpx.AsyncClient(timeout=_COMPLETION_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": request.prompt,
                    "stream": False,
                    "options": {"num_predict": request.max_output_tokens},
                },
            )
            response.raise_for_status()
            data = response.json()

        return CompletionResult(
            text=data.get("response", ""),
            provider=self.name,
            model=model,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )
