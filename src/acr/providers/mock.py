"""Deterministic mock provider.

No network calls; used as ACR's zero-config default and in the automated
test suite (master §1515: "Paid model access must not be required for the
normal test suite. Use mock providers.").
"""

from __future__ import annotations

from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider


class MockProvider(ModelProvider):
    name = "mock"

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        text = f"[mock:{len(request.prompt)} chars] {request.prompt[:120]}"
        return CompletionResult(
            text=text,
            provider=self.name,
            model="mock-echo-1",
            input_tokens=len(request.prompt.split()),
            output_tokens=len(text.split()),
        )

    async def is_available(self) -> bool:
        return True
