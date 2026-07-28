"""hot path indexes

Revision ID: ac998e062cab
Revises: 90f73bb6afb3
Create Date: 2026-07-28 16:06:56.928205

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ac998e062cab"
down_revision: str | Sequence[str] | None = "90f73bb6afb3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NOTE: Alembic's autogenerate diffs the FTS5 virtual tables' *shadow*
# tables (memory_fts_data/_idx/_docsize/_config, skills_fts_*) as spurious
# drops on every revision after the FTS5 migrations — they aren't declared
# via SQLAlchemy's Base.metadata, only created by raw SQL in
# acr.memory.fts/acr.skills.fts. This revision is hand-trimmed to keep only
# the real change: indexes on columns every hot-path query (memory
# retrieval, skill routing, the Phase 11 dashboard) already filters,
# groups, or orders by.


def upgrade() -> None:
    op.create_index(
        op.f("ix_agent_topology_records_task_class"),
        "agent_topology_records",
        ["task_class"],
        unique=False,
    )
    op.create_index(op.f("ix_memory_records_scope"), "memory_records", ["scope"], unique=False)
    op.create_index(op.f("ix_memory_records_status"), "memory_records", ["status"], unique=False)
    op.create_index(op.f("ix_memory_records_type"), "memory_records", ["type"], unique=False)
    op.create_index(op.f("ix_skills_status"), "skills", ["status"], unique=False)
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"], unique=False)
    op.create_index(
        op.f("ix_telemetry_events_created_at"), "telemetry_events", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_telemetry_events_event_type"), "telemetry_events", ["event_type"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_telemetry_events_event_type"), table_name="telemetry_events")
    op.drop_index(op.f("ix_telemetry_events_created_at"), table_name="telemetry_events")
    op.drop_index(op.f("ix_tasks_status"), table_name="tasks")
    op.drop_index(op.f("ix_skills_status"), table_name="skills")
    op.drop_index(op.f("ix_memory_records_type"), table_name="memory_records")
    op.drop_index(op.f("ix_memory_records_status"), table_name="memory_records")
    op.drop_index(op.f("ix_memory_records_scope"), table_name="memory_records")
    op.drop_index(op.f("ix_agent_topology_records_task_class"), table_name="agent_topology_records")
