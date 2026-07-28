"""Model provider abstraction.

Core runtime code must depend only on this interface, never on a specific
provider's SDK or wire format (master §139: "Do not hard-code provider
behavior into the core runtime.").
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    prompt: str
    max_output_tokens: int = 512


@dataclass(frozen=True, slots=True)
class CompletionResult:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class ModelProvider(ABC):
    """A model provider capable of producing text completions."""

    name: str

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResult: ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Cheap local/remote health check. Must never raise."""
        ...
