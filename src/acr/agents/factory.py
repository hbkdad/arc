"""Agent factory (master §747-772).

"Use the minimum number of agents required... Do not create agents for
visual spectacle or architectural complexity." A "spawned agent" in ACR is
a scoped `Task` run through the Phase 1 task engine — not a separate
execution primitive — so spawning is cheap to reason about and every agent
run gets the same telemetry/lifecycle guarantees a plain task does.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.critic import review_agent_task
from acr.agents.models import AgentSpec, SpawnEstimate
from acr.agents.topology import record_topology
from acr.core.execution import run_task
from acr.core.tasks.models import Task
from acr.evaluation.panel import PanelResult
from acr.learning.utility import record_skill_outcome
from acr.providers.base import ModelProvider
from acr.routing.models import ModelRouter, NoProviderAvailableError
from acr.telemetry.recorder import TelemetryRecorder

_COORDINATION_OVERHEAD_PER_GRANT = 0.05
_SECURITY_RISK_PER_PERMISSION = 0.05
_BASE_QUALITY_GAIN_UNSCOPED = 0.2
_BASE_QUALITY_GAIN_SCOPED = 0.5


class SpawnNotWorthwhileError(RuntimeError):
    """Raised by `spawn_agent()` when `estimate_spawn(spec)` says spawning
    isn't worth it and the caller didn't pass `force=True`."""

    def __init__(self, estimate: SpawnEstimate) -> None:
        self.estimate = estimate
        super().__init__(
            "estimate does not justify spawning "
            f"(quality_gain={estimate.expected_quality_gain:.2f}, "
            f"overhead+risk={estimate.coordination_overhead + estimate.security_risk:.2f})"
        )


def estimate_spawn(spec: AgentSpec) -> SpawnEstimate:
    """Deterministic v1 estimate (master §765-770).

    Coordination overhead and security risk both grow with how much a spec
    is granted (more tools/skills to coordinate, more permissions that
    could go wrong); `token_cost` is the spec's own declared budget;
    `latency_benefit` is 0 for a single agent — it only becomes positive
    once there's a real multi-agent baseline to compare against (topology
    history, not yet available for a spec that's never run).
    """
    coordination_overhead = _COORDINATION_OVERHEAD_PER_GRANT * (len(spec.tools) + len(spec.skills))
    security_risk = _SECURITY_RISK_PER_PERMISSION * len(spec.permissions)
    quality_gain = (
        _BASE_QUALITY_GAIN_SCOPED if (spec.tools or spec.skills) else _BASE_QUALITY_GAIN_UNSCOPED
    )

    return SpawnEstimate(
        expected_quality_gain=quality_gain,
        coordination_overhead=coordination_overhead,
        token_cost=spec.token_budget,
        latency_benefit=0.0,
        security_risk=security_risk,
    )


async def spawn_agent(
    session: AsyncSession,
    spec: AgentSpec,
    provider: ModelProvider,
    telemetry: TelemetryRecorder,
    *,
    task_class: str,
    force: bool = False,
) -> tuple[Task, PanelResult]:
    """Run `spec.objective` end to end via the task engine, then close the
    loop this module's docstring promises but previously never did.

    `learning.utility.record_skill_outcome()` (Phase 8) and
    `agents.topology.record_topology()` (Phase 10) both existed as real,
    tested functions with nothing in application code ever calling them --
    `routing.route()`'s "check prior performance" step and
    `topology.recommend_topology()`'s evidence requirement could
    therefore never see real data no matter how many agents actually ran.
    This was the one function positioned to close it for every caller at
    once (CLI today, any future caller) rather than leaving each call site
    to remember on its own -- how the gap arose in the first place.

    `task_class` is required, not inferred: ACR has no classifier model
    (see `skills.routing.route()`), so guessing one here would silently
    misattribute evidence to the wrong class, worse than not recording at
    all.

    Refuses to run when `estimate_spawn(spec)` says it isn't worth it,
    unless `force=True` -- this is the actual enforcement point for the
    cost/risk gate this module's docstring describes. It used to live only
    in the CLI's own `agents spawn` command (this function ran
    unconditionally), so any other caller would have silently bypassed it.
    """
    estimate = estimate_spawn(spec)
    if not estimate.worth_spawning and not force:
        raise SpawnNotWorthwhileError(estimate)

    task = await run_task(session, spec.objective, provider, telemetry)
    review = review_agent_task(task)

    await _record_evidence(
        session,
        spec=spec,
        task_class=task_class,
        model_names=[provider.name],
        review=review,
    )

    return task, review


async def spawn_agent_with_escalation(
    session: AsyncSession,
    spec: AgentSpec,
    router: ModelRouter,
    telemetry: TelemetryRecorder,
    *,
    task_class: str,
    min_quality_tier: int = 0,
    force: bool = False,
) -> tuple[Task, PanelResult]:
    """Like `spawn_agent()`, but starts at the cheapest tier `router` offers
    and only pays for a pricier one when the cheap attempt's own review
    fails, instead of running unconditionally on one pre-resolved provider.

    `routing.models.ModelRouter.complete_with_escalation()` already
    implements exactly this cheap-first/escalate-on-rejection tradeoff for a
    single completion, but nothing called it — `spawn_agent()` takes one
    resolved `provider` and never revisits that choice. Reusing it here
    would require threading a `verify` callback through `run_task()`'s
    internal `provider.complete()` call, which `run_task()` doesn't expose;
    reusing the same ascending-tier, skip-unavailable, skip-erroring
    candidate order at the whole-task level instead needs no change to
    `run_task()` or its Task/Step/telemetry model.

    Each tier tried is a real, separate `run_task()` call -- a failed cheap
    attempt is never hidden or merged into a single fabricated narrative;
    both the failed and the eventual successful task show up in telemetry
    and topology history exactly as they happened.
    """
    estimate = estimate_spawn(spec)
    if not estimate.worth_spawning and not force:
        raise SpawnNotWorthwhileError(estimate)

    tiers = sorted({p.quality_tier for p in router.profiles if p.quality_tier >= min_quality_tier})
    if not tiers:
        raise NoProviderAvailableError(f"no profile meets min_quality_tier={min_quality_tier}")

    tried_models: list[str] = []
    task: Task | None = None
    review: PanelResult | None = None
    for tier in tiers:
        profile = await router.select(min_quality_tier=tier)
        if profile.name in tried_models:
            continue
        tried_models.append(profile.name)
        task = await run_task(session, spec.objective, profile.provider, telemetry)
        review = review_agent_task(task)
        if review.passed:
            break

    assert task is not None and review is not None

    await _record_evidence(
        session, spec=spec, task_class=task_class, model_names=tried_models, review=review
    )

    return task, review


async def _record_evidence(
    session: AsyncSession,
    *,
    spec: AgentSpec,
    task_class: str,
    model_names: list[str],
    review: PanelResult,
) -> None:
    for skill_id in spec.skills:
        await record_skill_outcome(session, skill_id, success=review.passed)

    await record_topology(
        session,
        task_class=task_class,
        worker_count=1,
        model_names=model_names,
        skill_ids=spec.skills,
        quality_score=review.mean_score,
        succeeded=review.passed,
    )
