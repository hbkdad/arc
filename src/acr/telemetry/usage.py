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

from sqlalchemy import func, select
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
    never hidden for lack of a current price.

    Aggregated in SQL (`GROUP BY` over a `json_extract`'d provider name),
    not fetched-then-summed in Python -- this is called from `/routing`
    and `/api/graph` (the latter polled every 2s per its own docstring),
    so pulling and JSON-deserializing every `model.call.completed` row
    ever recorded on each poll would keep getting slower for as long as a
    local instance stays in real use, unlike every other dashboard query
    (all already `GROUP BY`/`LIMIT` at the SQL level)."""
    provider_col = TelemetryEvent.payload["provider"].as_string()
    input_tokens_col = TelemetryEvent.payload["input_tokens"].as_integer()
    output_tokens_col = TelemetryEvent.payload["output_tokens"].as_integer()

    stmt = (
        select(
            provider_col.label("provider"),
            func.count().label("calls"),
            func.coalesce(func.sum(input_tokens_col), 0).label("input_tokens"),
            func.coalesce(func.sum(output_tokens_col), 0).label("output_tokens"),
        )
        .where(TelemetryEvent.event_type == "model.call.completed")
        .where(provider_col.is_not(None))
        .group_by(provider_col)
    )
    rows = (await session.execute(stmt)).all()

    cost_by_name = {p.name: p.cost_per_1k_tokens for p in profiles}

    result: list[ProviderUsage] = []
    for provider, calls, input_tokens, output_tokens in rows:
        cost_per_1k = cost_by_name.get(provider)
        total_tokens = input_tokens + output_tokens
        estimated_cost = (total_tokens / 1000) * cost_per_1k if cost_per_1k is not None else None
        result.append(
            ProviderUsage(
                provider=provider,
                call_count=calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_per_1k_tokens=cost_per_1k,
                estimated_cost=estimated_cost,
            )
        )

    result.sort(key=lambda u: u.provider)
    return result
