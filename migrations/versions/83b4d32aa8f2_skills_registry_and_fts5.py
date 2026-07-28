"""skills registry and fts5

Revision ID: 83b4d32aa8f2
Revises: 6c384104b66a
Create Date: 2026-07-28 13:50:12.783395

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from acr.skills.fts import CREATE_STATEMENTS, DROP_STATEMENTS

# revision identifiers, used by Alembic.
revision: str = "83b4d32aa8f2"
down_revision: str | Sequence[str] | None = "6c384104b66a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "skills",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("task_classes", sa.JSON(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("models", sa.JSON(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("applicability", sa.String(), nullable=False),
        sa.Column("contraindications", sa.String(), nullable=False),
        sa.Column("verification", sa.String(), nullable=False),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "EXPERIMENTAL", "QUARANTINED", "ACTIVE", "DEPRECATED", "RETIRED", name="skillstatus"
            ),
            nullable=False,
        ),
        sa.Column("reliability", sa.Float(), nullable=False),
        sa.Column("successful_uses", sa.Integer(), nullable=False),
        sa.Column("failed_uses", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # NOTE: autogenerate also proposed dropping memory_fts and its FTS5 shadow
    # tables (memory_fts_data/idx/docsize/config) here. Those are raw-SQL
    # virtual tables from an earlier migration that Base.metadata doesn't
    # know about (they're not ORM models) — autogenerate's diff sees them as
    # "extra" and wants them gone. That drop was removed by hand; the
    # memory_fts family must survive this migration.

    # Hand-written: SQLite FTS5 virtual table + sync triggers over
    # skills.name/description, shared with tests via acr.skills.fts.
    for statement in CREATE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    """Downgrade schema."""
    for statement in DROP_STATEMENTS:
        op.execute(statement)

    op.drop_table("skills")
