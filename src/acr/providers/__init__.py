"""Model provider abstraction and implementations (master spec §133-139, §793-925)."""

from acr.providers.anthropic_compatible import AnthropicCompatibleProvider
from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider
from acr.providers.mock import MockProvider
from acr.providers.ollama import OllamaProvider
from acr.providers.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "AnthropicCompatibleProvider",
    "CompletionRequest",
    "CompletionResult",
    "MockProvider",
    "ModelProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
]
