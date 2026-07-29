"""Tests for acr.routing.models (master §794-825)."""

from __future__ import annotations

import pytest

from acr.config import Settings
from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider
from acr.routing.models import (
    ModelProfile,
    ModelRouter,
    NoProviderAvailableError,
    build_default_router,
)


class _FakeProvider(ModelProvider):
    """A test double: fixed availability and a fixed reply, no network."""

    def __init__(
        self, name: str, *, available: bool, reply: str, fail_with: Exception | None = None
    ) -> None:
        self.name = name
        self._available = available
        self._reply = reply
        self._fail_with = fail_with

    async def is_available(self) -> bool:
        return self._available

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if self._fail_with is not None:
            raise self._fail_with
        return CompletionResult(
            text=self._reply, provider=self.name, model=self.name, input_tokens=1, output_tokens=1
        )


def _profile(
    name: str,
    *,
    available: bool,
    reply: str,
    tier: int,
    cost: float = 0.0,
    fail_with: Exception | None = None,
) -> ModelProfile:
    return ModelProfile(
        provider=_FakeProvider(name, available=available, reply=reply, fail_with=fail_with),
        name=name,
        cost_per_1k_tokens=cost,
        quality_tier=tier,
    )


async def test_select_returns_cheapest_available_profile() -> None:
    router = ModelRouter(
        [
            _profile("expensive", available=True, reply="x", tier=0, cost=1.0),
            _profile("cheap", available=True, reply="x", tier=0, cost=0.1),
        ]
    )
    selected = await router.select()
    assert selected.name == "cheap"


async def test_select_skips_unavailable_profiles() -> None:
    router = ModelRouter(
        [
            _profile("cheap-but-down", available=False, reply="x", tier=0, cost=0.0),
            _profile("fallback", available=True, reply="x", tier=0, cost=1.0),
        ]
    )
    selected = await router.select()
    assert selected.name == "fallback"


async def test_select_raises_when_nothing_available() -> None:
    router = ModelRouter([_profile("down", available=False, reply="x", tier=0)])
    with pytest.raises(NoProviderAvailableError):
        await router.select()


async def test_complete_with_escalation_uses_cheapest_qualifying_model_first() -> None:
    router = ModelRouter(
        [
            _profile("local", available=True, reply="local reply", tier=0),
            _profile("cloud", available=True, reply="cloud reply", tier=1, cost=1.0),
        ]
    )
    routed = await router.complete_with_escalation(CompletionRequest(prompt="hi"))
    assert routed.result.text == "local reply"
    assert routed.tried_profiles == ["local"]
    assert routed.escalated is False


async def test_complete_with_escalation_escalates_on_verification_failure() -> None:
    router = ModelRouter(
        [
            _profile("local", available=True, reply="bad", tier=0),
            _profile("cloud", available=True, reply="good", tier=1, cost=1.0),
        ]
    )
    routed = await router.complete_with_escalation(
        CompletionRequest(prompt="hi"), verify=lambda result: result.text == "good"
    )
    assert routed.result.text == "good"
    assert routed.tried_profiles == ["local", "cloud"]
    assert routed.escalated is True


async def test_complete_with_escalation_returns_last_attempt_if_never_verified() -> None:
    router = ModelRouter(
        [
            _profile("local", available=True, reply="bad", tier=0),
            _profile("cloud", available=True, reply="still bad", tier=1, cost=1.0),
        ]
    )
    routed = await router.complete_with_escalation(
        CompletionRequest(prompt="hi"), verify=lambda result: False
    )
    assert routed.result.text == "still bad"
    assert routed.tried_profiles == ["local", "cloud"]


async def test_complete_with_escalation_raises_when_nothing_available() -> None:
    router = ModelRouter([_profile("down", available=False, reply="x", tier=0)])
    with pytest.raises(NoProviderAvailableError):
        await router.complete_with_escalation(CompletionRequest(prompt="hi"))


async def test_complete_with_escalation_moves_on_when_a_candidate_completion_fails() -> None:
    # is_available() only checks reachability -- a candidate can still fail
    # once actually asked to complete (Ollama with no model pulled, a cloud
    # provider timing out). The ladder must try the next candidate, not
    # blow up the whole call.
    router = ModelRouter(
        [
            _profile(
                "flaky",
                available=True,
                reply="unreachable",
                tier=0,
                fail_with=RuntimeError("boom"),
            ),
            _profile("fallback", available=True, reply="fallback reply", tier=1, cost=1.0),
        ]
    )
    routed = await router.complete_with_escalation(CompletionRequest(prompt="hi"))
    assert routed.result.text == "fallback reply"
    assert routed.tried_profiles == ["flaky", "fallback"]


async def test_complete_with_escalation_raises_with_the_last_error_when_every_candidate_fails() -> (
    None
):
    router = ModelRouter(
        [
            _profile("flaky-one", available=True, reply="x", tier=0, fail_with=RuntimeError("one")),
            _profile(
                "flaky-two",
                available=True,
                reply="x",
                tier=1,
                cost=1.0,
                fail_with=RuntimeError("two"),
            ),
        ]
    )
    with pytest.raises(NoProviderAvailableError, match="two"):
        await router.complete_with_escalation(CompletionRequest(prompt="hi"))


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
