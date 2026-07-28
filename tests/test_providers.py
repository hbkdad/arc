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


async def test_ollama_list_models_is_empty_when_unreachable() -> None:
    provider = OllamaProvider(base_url="http://127.0.0.1:1")
    assert await provider.list_models() == []


async def test_ollama_list_models_returns_strings_when_reachable() -> None:
    # Doesn't assert specific model names: passes whether or not Ollama is
    # actually installed in the environment running this test (an empty
    # list is a valid result too).
    provider = OllamaProvider()
    models = await provider.list_models()
    assert isinstance(models, list)
    assert all(isinstance(name, str) for name in models)
