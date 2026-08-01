"""Model routing (master §794-825).

Routing objective (§805-806): use the least expensive model expected to meet
the required quality threshold. Escalation (§807-812): try the cheapest
qualifying model first; if a caller-supplied `verify` rejects the result,
escalate to the next-higher-quality available model, and report which
models were tried so callers can track whether escalation improved the
outcome.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider


class NoProviderAvailableError(RuntimeError):
    """No configured, available provider meets the request."""


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """What ACR knows about one routable (provider, model) pair (master §795-804)."""

    provider: ModelProvider
    name: str
    cost_per_1k_tokens: float  # 0.0 for local/free
    quality_tier: int  # higher = more capable; used to order escalation


@dataclass(frozen=True, slots=True)
class RoutedCompletion:
    result: CompletionResult
    tried_profiles: list[str]
    escalated: bool


class ModelRouter:
    def __init__(self, profiles: list[ModelProfile]) -> None:
        self._profiles = list(profiles)

    @property
    def profiles(self) -> list[ModelProfile]:
        return list(self._profiles)

    async def availability(self) -> list[tuple[ModelProfile, bool]]:
        """Each profile paired with its live `is_available()` check --
        the CLI's `models list` and the dashboard's `/routing` page both
        need exactly this, and had each grown their own copy of the same
        list comprehension before this existed."""
        return [(profile, await profile.provider.is_available()) for profile in self._profiles]

    async def select(self, *, min_quality_tier: int = 0) -> ModelProfile:
        """The cheapest available profile meeting `min_quality_tier`."""
        candidates = sorted(
            (p for p in self._profiles if p.quality_tier >= min_quality_tier),
            key=lambda p: p.cost_per_1k_tokens,
        )
        for profile in candidates:
            if await profile.provider.is_available():
                return profile
        raise NoProviderAvailableError(
            f"no available provider meets min_quality_tier={min_quality_tier}"
        )

    async def complete_with_escalation(
        self,
        request: CompletionRequest,
        *,
        min_quality_tier: int = 0,
        verify: Callable[[CompletionResult], bool] | None = None,
    ) -> RoutedCompletion:
        """Try the cheapest qualifying model; escalate on `verify` failure.

        Escalation order is ascending `quality_tier` (cheap/local first),
        breaking ties by cost. Returns the last attempt if every candidate
        is exhausted without `verify` passing — an exhausted ladder isn't a
        failure ACR should raise on; the caller decides what to do with it.
        """
        candidates = sorted(
            (p for p in self._profiles if p.quality_tier >= min_quality_tier),
            key=lambda p: (p.quality_tier, p.cost_per_1k_tokens),
        )
        if not candidates:
            raise NoProviderAvailableError(f"no profile meets min_quality_tier={min_quality_tier}")

        tried: list[str] = []
        last_result: CompletionResult | None = None
        last_error: Exception | None = None
        for profile in candidates:
            if not await profile.provider.is_available():
                continue
            tried.append(profile.name)
            try:
                result = await profile.provider.complete(request)
            except Exception as exc:
                # is_available() only checks reachability, not that a
                # completion will actually succeed (e.g. Ollama has no model
                # pulled, a cloud provider times out or 5xxs) -- an
                # escalation ladder that aborts on the first such failure
                # defeats its own purpose, so treat it the same as an
                # unavailable candidate and move on.
                last_error = exc
                continue
            last_result = result
            if verify is None or verify(result):
                return RoutedCompletion(
                    result=result, tried_profiles=tried, escalated=len(tried) > 1
                )

        if last_result is None:
            if last_error is not None:
                raise NoProviderAvailableError(
                    f"no configured provider completed successfully: {last_error}"
                ) from last_error
            raise NoProviderAvailableError("no configured provider is available")
        return RoutedCompletion(result=last_result, tried_profiles=tried, escalated=len(tried) > 1)
