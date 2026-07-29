"""Per-provider usage and cost aggregation.

Read-only aggregation over `model.call.completed` `TelemetryEvent` rows
`core.execution.run_task()` already writes -- no new instrumentation
beyond adding `input_tokens` alongside the pre-existing `output_tokens`
in that same event, and no synthetic numbers. Cost is estimated by
multiplying real recorded tokens against the *current*
`ModelProfile.cost_per_1k_tokens` for that provider name -- there is no
historical price catalog, so a provider whose pricing changed since an
older call was made isn't retroactively re-priced. That's an
approximation stated plainly in every consumer of this module (CLI,
dashboard), not hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.routing.models import ModelProfile
from acr.telemetry.models import TelemetryEvent

__all__ = ["ProviderUsage", "usage_by_provider"]


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    provider: str
    call_count: int
    input_tokens: int
    output_tokens: int
    cost_per_1k_tokens: float | None
    estimated_cost: float | None


async def usage_by_provider(
    session: AsyncSession, profiles: list[ModelProfile]
) -> list[ProviderUsage]:
    """Real per-provider call counts and token totals from every recorded
    `model.call.completed` event, cross-referenced against `profiles`
    (typically `build_default_router(settings).profiles`) for pricing.
    A provider that has real usage but no longer has a configured
    `ModelProfile` (e.g. removed from the ladder) still appears, just with
    `cost_per_1k_tokens`/`estimated_cost` both `None` -- real usage is
    never hidden for lack of a current price."""
    stmt = select(TelemetryEvent).where(TelemetryEvent.event_type == "model.call.completed")
    events = list((await session.execute(stmt)).scalars().all())

    cost_by_name = {p.name: p.cost_per_1k_tokens for p in profiles}

    totals: dict[str, dict[str, int]] = {}
    for event in events:
        provider = event.payload.get("provider")
        if not isinstance(provider, str):
            continue
        bucket = totals.setdefault(provider, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        bucket["calls"] += 1
        input_tokens = event.payload.get("input_tokens")
        output_tokens = event.payload.get("output_tokens")
        bucket["input_tokens"] += input_tokens if isinstance(input_tokens, int) else 0
        bucket["output_tokens"] += output_tokens if isinstance(output_tokens, int) else 0

    result: list[ProviderUsage] = []
    for provider, bucket in totals.items():
        cost_per_1k = cost_by_name.get(provider)
        total_tokens = bucket["input_tokens"] + bucket["output_tokens"]
        estimated_cost = (total_tokens / 1000) * cost_per_1k if cost_per_1k is not None else None
        result.append(
            ProviderUsage(
                provider=provider,
                call_count=bucket["calls"],
                input_tokens=bucket["input_tokens"],
                output_tokens=bucket["output_tokens"],
                cost_per_1k_tokens=cost_per_1k,
                estimated_cost=estimated_cost,
            )
        )

    result.sort(key=lambda u: u.provider)
    return result
