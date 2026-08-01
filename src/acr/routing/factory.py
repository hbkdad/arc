"""Composition root for `ModelRouter` (master §794-825).

Split out of `routing.models` so that module can stay provider-agnostic --
`ModelRouter`/`ModelProfile` are domain logic (an escalation ladder over
whatever `ModelProvider`s it's given), while this module is the one place
that knows about every *concrete* provider ACR ships (mock, Ollama, the
cloud adapters). Per CLAUDE.md, core domain logic must not depend on
provider implementations; `build_default_router()` living in the same file
as `ModelRouter` meant importing the router pulled in every provider SDK
dependency, and unit-testing `ModelRouter` in isolation required this
factory to load too.
"""

from __future__ import annotations

from acr.config import Settings
from acr.providers.anthropic_compatible import AnthropicCompatibleProvider
from acr.providers.mock import MockProvider
from acr.providers.ollama import OllamaProvider
from acr.providers.openai_compatible import OpenAICompatibleProvider
from acr.routing.models import ModelProfile, ModelRouter

__all__ = ["build_default_router"]


def build_default_router(settings: Settings) -> ModelRouter:
    """The standard escalation ladder: mock (always available, tier 0) ->
    local Ollama (tier 1, free) -> configured cloud providers (tier 2, paid).

    Cloud profiles are included even without an API key — `ModelRouter`
    skips unavailable profiles via `is_available()`, so this list is "what
    ACR knows how to route to", not "what's currently usable".
    """
    return ModelRouter(
        [
            ModelProfile(
                provider=MockProvider(), name="mock", cost_per_1k_tokens=0.0, quality_tier=0
            ),
            ModelProfile(
                provider=OllamaProvider(model=settings.ollama_model),
                name="ollama",
                cost_per_1k_tokens=0.0,
                quality_tier=1,
            ),
            ModelProfile(
                provider=OpenAICompatibleProvider(api_key=settings.openai_api_key),
                name="openai_compatible",
                cost_per_1k_tokens=0.15,
                quality_tier=2,
            ),
            ModelProfile(
                provider=AnthropicCompatibleProvider(api_key=settings.anthropic_api_key),
                name="anthropic_compatible",
                cost_per_1k_tokens=0.25,
                quality_tier=2,
            ),
        ]
    )
