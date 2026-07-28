"""Tests for the model provider abstraction and implementations."""

from __future__ import annotations

from acr.providers.base import CompletionRequest
from acr.providers.mock import MockProvider
from acr.providers.ollama import OllamaProvider


async def test_mock_provider_completes_deterministically() -> None:
    provider = MockProvider()

    result = await provider.complete(CompletionRequest(prompt="hello world"))

    assert result.provider == "mock"
    assert "hello world" in result.text
    assert result.output_tokens > 0
    assert await provider.is_available() is True


async def test_ollama_provider_reports_unavailable_when_unreachable() -> None:
    provider = OllamaProvider(base_url="http://127.0.0.1:1")
    assert await provider.is_available() is False
