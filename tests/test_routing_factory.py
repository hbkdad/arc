"""Tests for acr.routing.factory (master §794-825)."""

from __future__ import annotations

from acr.config import Settings
from acr.routing.factory import build_default_router


def test_build_default_router_includes_mock_ollama_and_cloud_profiles() -> None:
    router = build_default_router(Settings())
    names = {p.name for p in router.profiles}
    assert names == {"mock", "ollama", "openai_compatible", "anthropic_compatible"}


async def test_build_default_router_mock_is_always_available() -> None:
    router = build_default_router(Settings())
    selected = await router.select()
    # mock is tier 0 cost 0.0 so it's always the cheapest available choice
    # unless ollama also happens to be reachable at cost 0.0 too — either
    # way, a low/no-cost local profile must win over any cloud profile.
    assert selected.cost_per_1k_tokens == 0.0
