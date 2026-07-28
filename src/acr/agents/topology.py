"""Agent topology history (master §774-793).

"Record successful orchestration structures... Reuse only when historical
evidence supports it." A single run is not evidence — `recommend_topology`
returns `None` until at least `min_samples` records exist for a task class.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import JSON, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from acr.db.base import Base

DEFAULT_MIN_SAMPLES = 3
DEFAULT_MIN_SUCCESS_RATE = 0.6


def _new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class AgentTopologyRecord(Base):
    """One recorded orchestration outcome (master §776-791's tracked fields)."""

    __tablename__ = "agent_topology_records"

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)
    task_class: Mapped[str] = mapped_column(index=True)
    worker_count: Mapped[int]
    model_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    skill_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    total_tokens: Mapped[int] = mapped_column(default=0)
    cost_estimate: Mapped[float] = mapped_column(default=0.0)
    latency_ms: Mapped[int] = mapped_column(default=0)
    quality_score: Mapped[float] = mapped_column(default=0.0)
    succeeded: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


async def record_topology(
    session: AsyncSession,
    *,
    task_class: str,
    worker_count: int,
    model_names: list[str],
    skill_ids: list[str],
    total_tokens: int = 0,
    cost_estimate: float = 0.0,
    latency_ms: int = 0,
    quality_score: float = 0.0,
    succeeded: bool = True,
) -> AgentTopologyRecord:
    record = AgentTopologyRecord(
        task_class=task_class,
        worker_count=worker_count,
        model_names=model_names,
        skill_ids=skill_ids,
        total_tokens=total_tokens,
        cost_estimate=cost_estimate,
        latency_ms=latency_ms,
        quality_score=quality_score,
        succeeded=succeeded,
    )
    session.add(record)
    await session.flush()
    return record


@dataclass(frozen=True, slots=True)
class TopologyRecommendation:
    task_class: str
    sample_count: int
    success_rate: float
    recommended_worker_count: int
    mean_quality_score: float
    detail: str


async def recommend_topology(
    session: AsyncSession,
    task_class: str,
    *,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    min_success_rate: float = DEFAULT_MIN_SUCCESS_RATE,
) -> TopologyRecommendation | None:
    """Recommend a worker count for `task_class`, or `None` if there isn't
    enough evidence (fewer than `min_samples` records) or the historical
    success rate is too low to trust."""
    stmt = select(AgentTopologyRecord).where(AgentTopologyRecord.task_class == task_class)
    records = list((await session.execute(stmt)).scalars().all())

    if len(records) < min_samples:
        return None

    successes = [r for r in records if r.succeeded]
    success_rate = len(successes) / len(records)
    if success_rate < min_success_rate or not successes:
        return None

    mean_worker_count = round(sum(r.worker_count for r in successes) / len(successes))
    mean_quality = sum(r.quality_score for r in successes) / len(successes)

    return TopologyRecommendation(
        task_class=task_class,
        sample_count=len(records),
        success_rate=success_rate,
        recommended_worker_count=mean_worker_count,
        mean_quality_score=mean_quality,
        detail=(
            f"{len(successes)}/{len(records)} successful runs "
            f"({success_rate:.0%}), mean quality {mean_quality:.2f}"
        ),
    )
