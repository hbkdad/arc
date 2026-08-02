"""Chat turn engine.

Reuses `ModelRouter` exactly as `acr run`'s CLI wiring does for one-shot
tasks -- select the cheapest available profile meeting the requested
quality tier, then call it -- just addressed at a persistent multi-turn
`ChatSession` instead of a single `Task`. A chat turn is a lighter-weight
shape than `Task` (no planning/verification lifecycle), so it's recorded
directly as `ChatMessage` rows rather than routed through the task engine.

Conversation history is assembled as a plain formatted transcript, not
run through the memory system's hybrid retrieval -- that answers "what's
relevant from everything ACR has ever seen", a different question from
"what did we just say in this conversation".

Message content is redacted before it's persisted (matching
`core.execution.run_task`'s Step-payload redaction), but sent to the
provider raw -- redaction protects what's stored on disk, not what the
user explicitly chose to send. History replayed into later prompts is
therefore always the already-redacted version: a secret is used once for
its own turn's live call, then never appears again, including to the
model itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.chat.models import ChatMessage, ChatRole, ChatSession
from acr.providers.base import CompletionRequest
from acr.routing.models import ModelRouter
from acr.security.secrets import redact_secrets
from acr.telemetry.recorder import TelemetryRecorder

__all__ = [
    "DEFAULT_HISTORY_WINDOW",
    "ChatSessionNotFoundError",
    "ChatTurn",
    "get_transcript",
    "list_sessions",
    "send_message",
]

DEFAULT_HISTORY_WINDOW = 20
_TITLE_MAX_LEN = 60


class ChatSessionNotFoundError(LookupError):
    """Raised when a `chat_session_id` doesn't exist."""


@dataclass(frozen=True, slots=True)
class ChatTurn:
    session_id: str
    reply: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


def _title_from(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= _TITLE_MAX_LEN:
        return collapsed
    return collapsed[: _TITLE_MAX_LEN - 1].rstrip() + "…"


def _format_prompt(history: list[ChatMessage], new_message: str) -> str:
    lines = [
        f"{'User' if msg.role == ChatRole.USER else 'Assistant'}: {msg.content}" for msg in history
    ]
    lines.append(f"User: {new_message}")
    lines.append("Assistant:")
    return "\n\n".join(lines)


async def _get_session(session: AsyncSession, chat_session_id: str) -> ChatSession:
    chat_session = await session.get(ChatSession, chat_session_id)
    if chat_session is None:
        raise ChatSessionNotFoundError(f"no chat session with id {chat_session_id!r}")
    return chat_session


async def send_message(
    session: AsyncSession,
    router: ModelRouter,
    telemetry: TelemetryRecorder,
    text: str,
    *,
    chat_session_id: str | None = None,
    min_quality_tier: int = 0,
    history_window: int = DEFAULT_HISTORY_WINDOW,
) -> ChatTurn:
    """Send one message in `chat_session_id`'s conversation (or start a new
    one if omitted), and return the assistant's reply.

    Provider selection is re-resolved on every call, not cached for the
    session, so a long-running REPL picks up a newly-configured key or a
    provider coming back online without needing to restart. Raises
    `ChatSessionNotFoundError` for a bad id and `NoProviderAvailableError`
    (from `acr.routing.models`) if nothing qualifies -- in both cases
    before anything is written, mirroring `acr run`.
    """
    if chat_session_id is not None:
        chat_session = await _get_session(session, chat_session_id)
    else:
        chat_session = None

    profile = await router.select(min_quality_tier=min_quality_tier)

    if chat_session is None:
        chat_session = ChatSession(title=_title_from(text))
        session.add(chat_session)
        await session.flush()
        history: list[ChatMessage] = []
        next_sequence = 0
    else:
        existing = list(
            (
                await session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.chat_session_id == chat_session.id)
                    .order_by(ChatMessage.sequence)
                )
            ).scalars()
        )
        next_sequence = len(existing)
        history = existing[-history_window:] if history_window > 0 else []

    prompt = _format_prompt(history, text)

    session.add(
        ChatMessage(
            chat_session_id=chat_session.id,
            sequence=next_sequence,
            role=ChatRole.USER,
            content=redact_secrets(text),
        )
    )
    # A new ChatMessage is a separate row -- inserting one doesn't emit an
    # UPDATE against `chat_sessions`, so the column's own `onupdate` never
    # fires on its own. Bump it explicitly so `list_sessions()`'s "most
    # recently active first" ordering reflects real activity, not just
    # creation time.
    chat_session.updated_at = datetime.now(UTC)
    await session.flush()

    try:
        result = await profile.provider.complete(CompletionRequest(prompt=prompt))
    except Exception as exc:
        await telemetry.emit(
            session, "model.call.failed", payload={"provider": profile.name, "error": str(exc)}
        )
        await session.commit()
        raise

    session.add(
        ChatMessage(
            chat_session_id=chat_session.id,
            sequence=next_sequence + 1,
            role=ChatRole.ASSISTANT,
            content=redact_secrets(result.text),
            provider=result.provider,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
    )
    await telemetry.emit(
        session,
        "model.call.completed",
        payload={
            "provider": result.provider,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        },
    )
    await session.commit()

    return ChatTurn(
        session_id=chat_session.id,
        reply=result.text,
        provider=result.provider,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


async def list_sessions(session: AsyncSession, *, limit: int = 20) -> list[ChatSession]:
    """Most recently updated sessions first."""
    rows = await session.execute(
        select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit)
    )
    return list(rows.scalars())


async def get_transcript(session: AsyncSession, chat_session_id: str) -> list[ChatMessage]:
    """Every message in a session, in order. Raises `ChatSessionNotFoundError`
    for an unknown id (distinct from an empty list, which would otherwise
    look identical to a typo'd id)."""
    await _get_session(session, chat_session_id)
    rows = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_session_id == chat_session_id)
        .order_by(ChatMessage.sequence)
    )
    return list(rows.scalars())
