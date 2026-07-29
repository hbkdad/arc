"""Routing-optimization evidence (extends the generic `Proposal` mechanism
in `acr.learning.proposals` -- see that module's own scope-boundary
docstring: a proposal may only ever recommend something this codebase can
already review/apply through an existing, gated mechanism).

Unlike skill evolution (which can safely auto-apply `promote_evolution()`),
there is no safe, gated mechanism to auto-apply a routing preference: the
only real lever is `Settings.default_min_quality_tier`, an environment
variable this process must never write to itself (the same boundary that
governs every other environment/credential change in this system). A
routing-optimization proposal is therefore evidence for a human to act on,
not something ACR ever applies on its own -- see `proposals._apply()`'s
`ROUTING_OPTIMIZATION` branch, a deliberate no-op.

The evidence itself is real: per-(task_class, model) success rate and mean
quality, computed from `AgentTopologyRecord` rows real `agents spawn` runs
wrote (see docs/ARCHITECTURE.md's "Closing the evidence loop") -- gated
the same way `agents.topology.recommend_topology()` gates its own
recommendation: no opinion below `min_samples` real recorded runs for a
given model.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.agents.topology import AgentTopologyRecord

DEFAULT_MIN_SAMPLES = 3

__all__ = [
    "DEFAULT_MIN_SAMPLES",
    "ModelOutcome",
    "RoutingComparison",
    "compare_models",
    "model_outcomes_for_task_class",
]


@dataclass(frozen=True, slots=True)
class ModelOutcome:
    model_name: str
    samples: int
    success_rate: float
    mean_quality: float


@dataclass(frozen=True, slots=True)
class RoutingComparison:
    task_class: str
    current_model: str
    candidate_model: str
    current: ModelOutcome
    candidate: ModelOutcome
    recommend_switch: bool
    reason: str


async def model_outcomes_for_task_class(
    session: AsyncSession, *, task_class: str, min_samples: int = DEFAULT_MIN_SAMPLES
) -> list[ModelOutcome]:
    """Real per-model outcome evidence for `task_class`. A model with fewer
    than `min_samples` recorded spawns is excluded entirely -- not shown
    with a low-confidence number, since master principle #22 forbids
    treating an under-evidenced count as an opinion at all."""
    stmt = select(AgentTopologyRecord).where(AgentTopologyRecord.task_class == task_class)
    rows = list((await session.execute(stmt)).scalars().all())

    by_model: dict[str, list[AgentTopologyRecord]] = defaultdict(list)
    for row in rows:
        for name in row.model_names:
            by_model[name].append(row)

    outcomes: list[ModelOutcome] = []
    for name, records in by_model.items():
        if len(records) < min_samples:
            continue
        successes = sum(1 for r in records if r.succeeded)
        outcomes.append(
            ModelOutcome(
                model_name=name,
                samples=len(records),
                success_rate=successes / len(records),
                mean_quality=sum(r.quality_score for r in records) / len(records),
            )
        )
    return outcomes


def compare_models(
    current: ModelOutcome, candidate: ModelOutcome, *, task_class: str
) -> RoutingComparison:
    """Recommend switching only if `candidate` is strictly better than
    `current` on *both* dimensions -- unlike skill-version comparison
    (where "not worse" is enough to keep a free lateral move), moving to a
    different model tier for routing has a real cost/risk difference, so
    the bar is real improvement, not just non-regression."""
    quality_improved = candidate.mean_quality > current.mean_quality
    success_improved = candidate.success_rate > current.success_rate
    recommend_switch = quality_improved and success_improved

    if recommend_switch:
        reason = (
            f"{candidate.model_name} outperforms {current.model_name} on both "
            f"success_rate ({candidate.success_rate:.2f} vs {current.success_rate:.2f}) "
            f"and mean_quality ({candidate.mean_quality:.2f} vs {current.mean_quality:.2f}) "
            f"for task_class={task_class!r} ({candidate.samples} vs {current.samples} samples)"
        )
    else:
        reason = (
            f"{candidate.model_name} does not clearly outperform {current.model_name} "
            f"for task_class={task_class!r} on real evidence so far"
        )

    return RoutingComparison(
        task_class=task_class,
        current_model=current.model_name,
        candidate_model=candidate.model_name,
        current=current,
        candidate=candidate,
        recommend_switch=recommend_switch,
        reason=reason,
    )
