"""dashboard sort column indexes

Revision ID: b0f49da0fea8
Revises: f0aa4f554248
Create Date: 2026-07-29 11:25:25.623427

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b0f49da0fea8"
down_revision: str | Sequence[str] | None = "f0aa4f554248"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NOTE: hand-trimmed for the same reason as ac998e062cab_hot_path_indexes.py
# -- Alembic's autogenerate diffs the FTS5 virtual tables' shadow tables as
# spurious drops on every revision, since they're only created by raw SQL
# in acr.memory.fts/acr.skills.fts, never declared via Base.metadata.
#
# The real change: the earlier hot-path-indexes migration indexed the
# columns the dashboard's queries *filter*/*group* by (status, type, scope,
# task_class) but missed the columns those same queries *order by* --
# `queries.py`'s recent_tasks()/recent_memories()/recent_topology()/
# recent_benchmark_runs() all do `ORDER BY <this column> DESC LIMIT N`, and
# without an index that's a full-table scan + sort on every dashboard poll
# (the visualization page hits `/api/graph` every 2s while open).


def upgrade() -> None:
    op.create_index(
        op.f("ix_agent_topology_records_created_at"),
        "agent_topology_records",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_benchmark_runs_created_at"), "benchmark_runs", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_memory_records_updated_at"), "memory_records", ["updated_at"], unique=False
    )
    op.create_index(op.f("ix_tasks_created_at"), "tasks", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_created_at"), table_name="tasks")
    op.drop_index(op.f("ix_memory_records_updated_at"), table_name="memory_records")
    op.drop_index(op.f("ix_benchmark_runs_created_at"), table_name="benchmark_runs")
    op.drop_index(op.f("ix_agent_topology_records_created_at"), table_name="agent_topology_records")
