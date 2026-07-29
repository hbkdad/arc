"""Tests for acr.telemetry.usage."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.core.execution import run_task
from acr.providers.mock import MockProvider
from acr.routing.models import ModelProfile
from acr.telemetry.recorder import TelemetryRecorder
from acr.telemetry.usage import usage_by_provider


async def test_returns_empty_list_with_no_calls_recorded(db_session: AsyncSession) -> None:
    usage = await usage_by_provider(db_session, [])

    assert usage == []


async def test_aggregates_real_calls_for_one_provider(db_session: AsyncSession) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())
    await run_task(db_session, "say hello again", MockProvider(), TelemetryRecorder())

    profiles = [
        ModelProfile(provider=MockProvider(), name="mock", cost_per_1k_tokens=0.0, quality_tier=0)
    ]
    usage = await usage_by_provider(db_session, profiles)

    assert len(usage) == 1
    assert usage[0].provider == "mock"
    assert usage[0].call_count == 2
    assert usage[0].input_tokens > 0
    assert usage[0].output_tokens > 0
    assert usage[0].cost_per_1k_tokens == 0.0
    assert usage[0].estimated_cost == 0.0


async def test_estimates_cost_for_a_priced_provider(db_session: AsyncSession) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    profiles = [
        ModelProfile(provider=MockProvider(), name="mock", cost_per_1k_tokens=1.0, quality_tier=0)
    ]
    usage = await usage_by_provider(db_session, profiles)

    assert len(usage) == 1
    total_tokens = usage[0].input_tokens + usage[0].output_tokens
    assert usage[0].estimated_cost == (total_tokens / 1000) * 1.0


async def test_a_provider_with_real_usage_but_no_current_profile_shows_no_cost(
    db_session: AsyncSession,
) -> None:
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    # No ModelProfile passed for "mock" at all -- usage must still show up,
    # just without a cost estimate, never hidden for lack of a price.
    usage = await usage_by_provider(db_session, [])

    assert len(usage) == 1
    assert usage[0].provider == "mock"
    assert usage[0].call_count == 1
    assert usage[0].cost_per_1k_tokens is None
    assert usage[0].estimated_cost is None


async def test_results_are_sorted_by_provider_name(db_session: AsyncSession) -> None:
    from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider

    class _ZProvider(ModelProvider):
        name = "zzz-provider"

        async def is_available(self) -> bool:
            return True

        async def complete(self, request: CompletionRequest) -> CompletionResult:
            return CompletionResult(
                text="ok", provider=self.name, model="z", input_tokens=1, output_tokens=1
            )

    await run_task(db_session, "say hello", _ZProvider(), TelemetryRecorder())
    await run_task(db_session, "say hello", MockProvider(), TelemetryRecorder())

    usage = await usage_by_provider(db_session, [])

    assert [u.provider for u in usage] == ["mock", "zzz-provider"]
