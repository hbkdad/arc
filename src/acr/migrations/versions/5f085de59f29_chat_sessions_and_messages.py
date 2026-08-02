"""chat sessions and messages

Revision ID: 5f085de59f29
Revises: b0f49da0fea8
Create Date: 2026-08-01 20:13:56.760189

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f085de59f29"
down_revision: str | Sequence[str] | None = "b0f49da0fea8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NOTE: same as every migration since the FTS5 ones -- autogenerate flags
# the memory_fts/skills_fts shadow tables as spurious drops (they're raw-SQL
# virtual tables, not SQLAlchemy-declared). Hand-trimmed to keep only the
# real change: the new `chat_sessions`/`chat_messages` tables.


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chat_sessions_created_at"), "chat_sessions", ["created_at"], unique=False
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("chat_session_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.Enum("USER", "ASSISTANT", name="chatrole"), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chat_messages_chat_session_id"),
        "chat_messages",
        ["chat_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_messages_created_at"), "chat_messages", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_messages_created_at"), table_name="chat_messages")
    op.drop_index(op.f("ix_chat_messages_chat_session_id"), table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index(op.f("ix_chat_sessions_created_at"), table_name="chat_sessions")
    op.drop_table("chat_sessions")
