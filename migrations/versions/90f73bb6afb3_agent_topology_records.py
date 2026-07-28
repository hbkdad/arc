"""agent topology records

Revision ID: 90f73bb6afb3
Revises: 5a8d4f37fff6
Create Date: 2026-07-28 15:33:00.749652

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "90f73bb6afb3"
down_revision: str | Sequence[str] | None = "5a8d4f37fff6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_topology_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_class", sa.String(), nullable=False),
        sa.Column("worker_count", sa.Integer(), nullable=False),
        sa.Column("model_names", sa.JSON(), nullable=False),
        sa.Column("skill_ids", sa.JSON(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_estimate", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # NOTE: autogenerate also proposed dropping the memory_fts and skills_fts
    # families (raw-SQL virtual tables Base.metadata doesn't know about —
    # see the same note in every prior migration touching this). Removed by
    # hand.


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("agent_topology_records")
