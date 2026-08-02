"""Tests for acr.chat.engine."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acr.chat.engine import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    ChatSessionNotFoundError,
    send_message,
)
from acr.chat.models import ChatMessage, ChatRole, ChatSession
from acr.providers.base import CompletionRequest, CompletionResult, ModelProvider
from acr.providers.mock import MockProvider
from acr.routing.models import ModelProfile, ModelRouter, NoProviderAvailableError
from acr.telemetry.models import TelemetryEvent
from acr.telemetry.recorder import TelemetryRecorder


class _AlwaysFailsProvider(ModelProvider):
    name = "always-fails"

    async def is_available(self) -> bool:
        return True

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        raise RuntimeError("simulated provider failure")


class _CapturingProvider(ModelProvider):
    """Records the exact `CompletionRequest` it was called with."""

    name = "capturing"

    def __init__(self) -> None:
        self.last_request: CompletionRequest | None = None

    async def is_available(self) -> bool:
        return True

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.last_request = request
        return CompletionResult(
            text="ok", provider=self.name, model="capture-1", input_tokens=1, output_tokens=1
        )


def _mock_router() -> ModelRouter:
    return ModelRouter(
        [ModelProfile(provider=MockProvider(), name="mock", cost_per_1k_tokens=0.0, quality_tier=0)]
    )


async def test_send_message_starts_a_new_session_and_persists_both_turns(
    db_session: AsyncSession,
) -> None:
    turn = await send_message(db_session, _mock_router(), TelemetryRecorder(), "hello there")

    messages = (
        (
            await db_session.execute(
                select(ChatMessage)
                .where(ChatMessage.chat_session_id == turn.session_id)
                .order_by(ChatMessage.sequence)
            )
        )
        .scalars()
        .all()
    )
    assert [m.role for m in messages] == [ChatRole.USER, ChatRole.ASSISTANT]
    assert messages[0].content == "hello there"
    assert messages[1].content == turn.reply
    assert messages[1].provider == "mock"
    assert messages[1].model == "mock-echo-1"
    assert messages[1].input_tokens is not None
    assert messages[0].sequence == 0
    assert messages[1].sequence == 1


async def test_send_message_derives_a_title_from_the_first_message(
    db_session: AsyncSession,
) -> None:
    turn = await send_message(db_session, _mock_router(), TelemetryRecorder(), "  what's  up  ")

    session_row = await db_session.get(ChatSession, turn.session_id)
    assert session_row is not None
    assert session_row.title == "what's up"


async def test_send_message_resumes_an_existing_session_and_orders_sequence(
    db_session: AsyncSession,
) -> None:
    router = _mock_router()
    telemetry = TelemetryRecorder()
    first = await send_message(db_session, router, telemetry, "first message")
    second = await send_message(
        db_session, router, telemetry, "second message", chat_session_id=first.session_id
    )

    assert second.session_id == first.session_id
    messages = (
        (
            await db_session.execute(
                select(ChatMessage)
                .where(ChatMessage.chat_session_id == first.session_id)
                .order_by(ChatMessage.sequence)
            )
        )
        .scalars()
        .all()
    )
    assert [m.sequence for m in messages] == [0, 1, 2, 3]
    assert messages[2].content == "second message"


async def test_send_message_includes_prior_turns_in_the_prompt(db_session: AsyncSession) -> None:
    # MockProvider echoes back a prefix of the exact prompt it received --
    # a real assertion that history assembly actually happened, not just
    # that the code path ran without error.
    router = _mock_router()
    telemetry = TelemetryRecorder()
    first = await send_message(db_session, router, telemetry, "my favorite color is teal")
    second = await send_message(
        db_session, router, telemetry, "what did I just say?", chat_session_id=first.session_id
    )

    assert "my favorite color is teal" in second.reply


async def test_send_message_raises_for_unknown_session_id(db_session: AsyncSession) -> None:
    try:
        await send_message(
            db_session, _mock_router(), TelemetryRecorder(), "hi", chat_session_id="does-not-exist"
        )
        raise AssertionError("expected ChatSessionNotFoundError")
    except ChatSessionNotFoundError:
        pass


async def test_send_message_raises_when_no_provider_available_and_writes_nothing(
    db_session: AsyncSession,
) -> None:
    router = _mock_router()  # only a tier-0 profile
    try:
        await send_message(db_session, router, TelemetryRecorder(), "hi", min_quality_tier=5)
        raise AssertionError("expected NoProviderAvailableError")
    except NoProviderAvailableError:
        pass

    sessions = (await db_session.execute(select(ChatSession))).scalars().all()
    assert sessions == []


async def test_send_message_records_telemetry_on_success(db_session: AsyncSession) -> None:
    await send_message(db_session, _mock_router(), TelemetryRecorder(), "hello")

    events = (await db_session.execute(select(TelemetryEvent))).scalars().all()
    event_types = [e.event_type for e in events]
    assert "model.call.completed" in event_types
    completed = next(e for e in events if e.event_type == "model.call.completed")
    assert completed.payload["provider"] == "mock"


async def test_send_message_records_failure_telemetry_and_keeps_the_user_turn(
    db_session: AsyncSession,
) -> None:
    router = ModelRouter(
        [
            ModelProfile(
                provider=_AlwaysFailsProvider(),
                name="always-fails",
                cost_per_1k_tokens=0.0,
                quality_tier=0,
            )
        ]
    )

    try:
        await send_message(db_session, router, TelemetryRecorder(), "hello")
        raise AssertionError("expected RuntimeError to propagate")
    except RuntimeError:
        pass

    events = (await db_session.execute(select(TelemetryEvent))).scalars().all()
    assert "model.call.failed" in [e.event_type for e in events]

    # The user's own message must survive a provider failure -- only the
    # assistant reply is missing, not the whole turn.
    messages = (await db_session.execute(select(ChatMessage))).scalars().all()
    assert len(messages) == 1
    assert messages[0].role == ChatRole.USER


async def test_send_message_redacts_secrets_in_stored_content(db_session: AsyncSession) -> None:
    secret_message = "my key is sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX, help me"
    turn = await send_message(db_session, _mock_router(), TelemetryRecorder(), secret_message)

    messages = (
        (
            await db_session.execute(
                select(ChatMessage)
                .where(ChatMessage.chat_session_id == turn.session_id)
                .order_by(ChatMessage.sequence)
            )
        )
        .scalars()
        .all()
    )
    assert "sk-ant-api03-" not in messages[0].content
    assert "[REDACTED]" in messages[0].content
    assert "sk-ant-api03-" not in messages[1].content


async def test_send_message_requests_a_generous_output_token_ceiling_by_default(
    db_session: AsyncSession,
) -> None:
    # A real bug: CompletionRequest's own default (512) reliably cut off a
    # substantive reply (e.g. "write me a full HTML page") mid-generation.
    # send_message() must ask for real headroom instead of inheriting that
    # default silently.
    provider = _CapturingProvider()
    router = ModelRouter(
        [ModelProfile(provider=provider, name="capturing", cost_per_1k_tokens=0.0, quality_tier=0)]
    )

    await send_message(db_session, router, TelemetryRecorder(), "write me something long")

    assert provider.last_request is not None
    assert provider.last_request.max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS
    assert provider.last_request.max_output_tokens > 512
