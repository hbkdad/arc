"""benchmark runs

Revision ID: 5a8d4f37fff6
Revises: 83b4d32aa8f2
Create Date: 2026-07-28 14:18:56.212985

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5a8d4f37fff6"
down_revision: str | Sequence[str] | None = "83b4d32aa8f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "benchmark_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("suite_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # NOTE: autogenerate also proposed dropping the memory_fts and skills_fts
    # families (raw-SQL virtual tables Base.metadata doesn't know about —
    # see the same note in 6c384104b66a and 83b4d32aa8f2). Removed by hand.


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("benchmark_runs")
