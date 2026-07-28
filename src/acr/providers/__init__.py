"""Model provider abstraction and implementations (master spec §133-139, §793-824)."""

from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider
from acr.providers.mock import MockProvider
from acr.providers.ollama import OllamaProvider

__all__ = [
    "CompletionRequest",
    "CompletionResult",
    "MockProvider",
    "ModelProvider",
    "OllamaProvider",
]
