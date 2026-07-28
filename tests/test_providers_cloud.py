"""Tests for the cloud-compatible providers (master §893-896).

No real network calls: `is_available()` short-circuits on a missing API key
before ever touching the network, so these are fully deterministic.
"""

from __future__ import annotations

import pytest

from acr.providers.anthropic_compatible import AnthropicCompatibleProvider
from acr.providers.base import CompletionRequest
from acr.providers.openai_compatible import OpenAICompatibleProvider


async def test_openai_compatible_unavailable_without_api_key() -> None:
    provider = OpenAICompatibleProvider(api_key=None)
    assert await provider.is_available() is False


async def test_openai_compatible_available_with_api_key() -> None:
    provider = OpenAICompatibleProvider(api_key="sk-fake")
    assert await provider.is_available() is True


async def test_openai_compatible_complete_without_key_raises() -> None:
    provider = OpenAICompatibleProvider(api_key=None)
    with pytest.raises(RuntimeError, match="requires an API key"):
        await provider.complete(CompletionRequest(prompt="hi"))


async def test_anthropic_compatible_unavailable_without_api_key() -> None:
    provider = AnthropicCompatibleProvider(api_key=None)
    assert await provider.is_available() is False


async def test_anthropic_compatible_available_with_api_key() -> None:
    provider = AnthropicCompatibleProvider(api_key="sk-ant-fake")
    assert await provider.is_available() is True


async def test_anthropic_compatible_complete_without_key_raises() -> None:
    provider = AnthropicCompatibleProvider(api_key=None)
    with pytest.raises(RuntimeError, match="requires an API key"):
        await provider.complete(CompletionRequest(prompt="hi"))
