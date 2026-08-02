"""Chat session ORM models.

A `ChatSession` is a persistent multi-turn conversation; each turn is two
`ChatMessage` rows (user, then assistant). This is deliberately separate
from `acr.core.tasks.models.Task` -- a task is a single objective run
through a validated lifecycle, while a chat turn is a lightweight
request/response pair with no planning/verification stages of its own.
Reusing `Task` would mean forcing every turn through a state machine built
for a different shape of work.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acr.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatSession(Base):
    """One persistent conversation. `title` is derived from the first
    user message so `acr chat list` has something readable to show."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)
    title: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.sequence"
    )


class ChatMessage(Base):
    """One turn's user or assistant message. `provider`/`model`/token
    counts are populated on assistant messages only (`None` on user
    messages) -- real values from `CompletionResult`, never estimated."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)
    chat_session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    sequence: Mapped[int]
    role: Mapped[ChatRole] = mapped_column(SAEnum(ChatRole))
    content: Mapped[str]
    provider: Mapped[str | None] = mapped_column(default=None)
    model: Mapped[str | None] = mapped_column(default=None)
    input_tokens: Mapped[int | None] = mapped_column(default=None)
    output_tokens: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)

    session: Mapped[ChatSession] = relationship(back_populates="messages")
