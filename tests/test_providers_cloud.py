"""Tests for the cloud-compatible providers (master §893-896).

`is_available()` short-circuits on a missing API key before ever touching
the network, so those cases are fully deterministic with no server needed.
`complete()`'s actual request/response handling is exercised against real,
ephemeral, localhost-only fake servers speaking each provider's wire format
(same pattern as `test_providers.py`'s fake Ollama server) rather than
mocked — this is where a real wire-format bug would actually show up.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from acr.providers.anthropic_compatible import AnthropicCompatibleProvider
from acr.providers.base import CompletionRequest
from acr.providers.openai_compatible import OpenAICompatibleProvider


async def test_openai_compatible_unavailable_without_api_key() -> None:
    provider = OpenAICompatibleProvider(api_key=None)
    assert await provider.is_available() is False


async def test_openai_compatible_available_with_api_key() -> None:
    provider = OpenAICompatibleProvider(api_key="sk-fake")
    assert await provider.is_available() is True


async def test_openai_compatible_complete_without_key_raises() -> None:
    provider = OpenAICompatibleProvider(api_key=None)
    with pytest.raises(RuntimeError, match="requires an API key"):
        await provider.complete(CompletionRequest(prompt="hi"))


async def test_anthropic_compatible_unavailable_without_api_key() -> None:
    provider = AnthropicCompatibleProvider(api_key=None)
    assert await provider.is_available() is False


async def test_anthropic_compatible_available_with_api_key() -> None:
    provider = AnthropicCompatibleProvider(api_key="sk-ant-fake")
    assert await provider.is_available() is True


async def test_anthropic_compatible_complete_without_key_raises() -> None:
    provider = AnthropicCompatibleProvider(api_key=None)
    with pytest.raises(RuntimeError, match="requires an API key"):
        await provider.complete(CompletionRequest(prompt="hi"))


class _RecordingHandler(BaseHTTPRequestHandler):
    """Records the last request and replies with a canned, provider-shaped body."""

    response_body: bytes = b"{}"
    last_path: str | None = None
    last_headers: dict[str, str] | None = None
    last_json: dict | None = None

    def do_POST(self) -> None:
        type(self).last_path = self.path
        type(self).last_headers = dict(self.headers)
        length = int(self.headers.get("Content-Length", 0))
        type(self).last_json = json.loads(self.rfile.read(length))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(type(self).response_body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def fake_http_server() -> Iterator[tuple[str, type[_RecordingHandler]]]:
    """Base URL of a real, ephemeral, localhost-only fake HTTP server.

    Yields `(base_url, handler_class)` -- set `handler_class.response_body`
    before a request, then inspect `handler_class.last_*` afterward.
    """

    class Handler(_RecordingHandler):
        pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", Handler
    finally:
        server.shutdown()
        thread.join()


async def test_anthropic_compatible_complete_parses_response_and_sends_auth(
    fake_http_server: tuple[str, type[_RecordingHandler]],
) -> None:
    base_url, handler = fake_http_server
    handler.response_body = json.dumps(
        {
            "content": [{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}],
            "usage": {"input_tokens": 7, "output_tokens": 3},
        }
    ).encode()
    provider = AnthropicCompatibleProvider(api_key="sk-ant-fake", base_url=base_url)

    result = await provider.complete(CompletionRequest(prompt="hi", max_output_tokens=128))

    assert result.text == "hello world"
    assert result.input_tokens == 7
    assert result.output_tokens == 3
    assert result.provider == "anthropic_compatible"
    assert handler.last_path == "/messages"
    assert handler.last_headers is not None
    assert handler.last_headers["x-api-key"] == "sk-ant-fake"
    assert handler.last_json is not None
    assert handler.last_json["messages"] == [{"role": "user", "content": "hi"}]
    assert handler.last_json["max_tokens"] == 128


async def test_openai_compatible_complete_parses_response_and_sends_auth(
    fake_http_server: tuple[str, type[_RecordingHandler]],
) -> None:
    base_url, handler = fake_http_server
    handler.response_body = json.dumps(
        {
            "choices": [{"message": {"role": "assistant", "content": "hi there"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }
    ).encode()
    provider = OpenAICompatibleProvider(api_key="sk-fake", base_url=base_url)

    result = await provider.complete(CompletionRequest(prompt="hi", max_output_tokens=64))

    assert result.text == "hi there"
    assert result.input_tokens == 5
    assert result.output_tokens == 2
    assert result.provider == "openai_compatible"
    assert handler.last_path == "/chat/completions"
    assert handler.last_headers is not None
    assert handler.last_headers["Authorization"] == "Bearer sk-fake"
    assert handler.last_json is not None
    assert handler.last_json["messages"] == [{"role": "user", "content": "hi"}]
    assert handler.last_json["max_tokens"] == 64


async def test_openai_compatible_complete_degrades_gracefully_on_an_empty_choices_list(
    fake_http_server: tuple[str, type[_RecordingHandler]],
) -> None:
    # A response that's valid JSON but doesn't have the expected shape (an
    # empty `choices`, or a function-call-only response with no `content`)
    # must produce an empty completion, not a raw KeyError/IndexError --
    # consistent with anthropic_compatible.py, which already handles the
    # equivalent case defensively.
    base_url, handler = fake_http_server
    handler.response_body = json.dumps({"choices": [], "usage": {}}).encode()
    provider = OpenAICompatibleProvider(api_key="sk-fake", base_url=base_url)

    result = await provider.complete(CompletionRequest(prompt="hi"))

    assert result.text == ""
