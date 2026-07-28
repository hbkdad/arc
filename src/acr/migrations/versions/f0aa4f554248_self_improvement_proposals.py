"""self improvement proposals

Revision ID: f0aa4f554248
Revises: ac998e062cab
Create Date: 2026-07-28 17:49:18.194293

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0aa4f554248"
down_revision: str | Sequence[str] | None = "ac998e062cab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NOTE: same as every migration since the FTS5 ones — autogenerate flags the
# memory_fts/skills_fts shadow tables as spurious drops (they're raw-SQL
# virtual tables, not SQLAlchemy-declared). Hand-trimmed to keep only the
# real change: the new `proposals` table.


def upgrade() -> None:
    op.create_table(
        "proposals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "kind", sa.Enum("SKILL_EVOLUTION_PROMOTION", name="proposalkind"), nullable=False
        ),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "REJECTED", "AUTO_APPLIED", name="proposalstatus"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_proposals_status"), "proposals", ["status"], unique=False)
    op.create_index(op.f("ix_proposals_subject"), "proposals", ["subject"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_proposals_subject"), table_name="proposals")
    op.drop_index(op.f("ix_proposals_status"), table_name="proposals")
    op.drop_table("proposals")
