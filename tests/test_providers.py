"""Tests for the model provider abstraction and implementations."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from acr.providers.base import CompletionRequest
from acr.providers.mock import MockProvider
from acr.providers.ollama import (
    _AVAILABILITY_TIMEOUT_SECONDS,
    _COMPLETION_TIMEOUT_SECONDS,
    OllamaNoModelError,
    OllamaProvider,
)


async def test_mock_provider_completes_deterministically() -> None:
    provider = MockProvider()

    result = await provider.complete(CompletionRequest(prompt="hello world"))

    assert result.provider == "mock"
    assert "hello world" in result.text
    assert result.output_tokens > 0
    assert await provider.is_available() is True


async def test_ollama_provider_reports_unavailable_when_unreachable() -> None:
    provider = OllamaProvider(base_url="http://127.0.0.1:1")
    assert await provider.is_available() is False


async def test_ollama_list_models_is_empty_when_unreachable() -> None:
    provider = OllamaProvider(base_url="http://127.0.0.1:1")
    assert await provider.list_models() == []


async def test_ollama_list_models_returns_strings_when_reachable() -> None:
    # Doesn't assert specific model names: passes whether or not Ollama is
    # actually installed in the environment running this test (an empty
    # list is a valid result too).
    provider = OllamaProvider()
    models = await provider.list_models()
    assert isinstance(models, list)
    assert all(isinstance(name, str) for name in models)


class _FakeOllamaHandler(BaseHTTPRequestHandler):
    """Mimics just enough of the real Ollama API to test model resolution
    without depending on a real local Ollama install being present."""

    models: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        body = json.dumps({"models": [{"name": m} for m in self.models]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length))
        body = json.dumps(
            {
                "response": f"echo:{request['model']}",
                "prompt_eval_count": 3,
                "eval_count": 2,
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def fake_ollama_server() -> Iterator[tuple[str, list[str]]]:
    """Base URL of a real, ephemeral, localhost-only fake Ollama daemon.

    Yields `(base_url, models)` — mutate `models` before a request to
    control what `/api/tags` reports.
    """
    models: list[str] = []

    class Handler(_FakeOllamaHandler):
        pass

    Handler.models = models  # shared reference, mutable by the test
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", models
    finally:
        server.shutdown()
        thread.join()


async def test_ollama_complete_auto_detects_the_first_available_model(
    fake_ollama_server: tuple[str, list[str]],
) -> None:
    base_url, models = fake_ollama_server
    models.extend(["qwen2.5-coder:1.5b", "llama3.1:8b"])
    provider = OllamaProvider(base_url=base_url)  # model=None: auto-detect

    result = await provider.complete(CompletionRequest(prompt="hi"))

    assert result.model == "qwen2.5-coder:1.5b"
    assert result.text == "echo:qwen2.5-coder:1.5b"


async def test_ollama_complete_uses_an_explicitly_configured_model(
    fake_ollama_server: tuple[str, list[str]],
) -> None:
    base_url, models = fake_ollama_server
    models.extend(["qwen2.5-coder:1.5b"])  # present but should be ignored
    provider = OllamaProvider(base_url=base_url, model="llama3.1:8b")

    result = await provider.complete(CompletionRequest(prompt="hi"))

    assert result.model == "llama3.1:8b"


async def test_ollama_complete_raises_a_clear_error_with_no_models_pulled(
    fake_ollama_server: tuple[str, list[str]],
) -> None:
    base_url, _models = fake_ollama_server  # no models pulled
    provider = OllamaProvider(base_url=base_url)

    with pytest.raises(OllamaNoModelError, match="ollama pull"):
        await provider.complete(CompletionRequest(prompt="hi"))


def test_ollama_timeouts_stay_generous_for_real_unaccelerated_hardware() -> None:
    # Regression guard, not a behavioral test: both constants were raised
    # after being measured as genuinely too tight against real local
    # hardware (1.0s availability timeout false-negatived a running daemon
    # due to ~1-7s httpx cold-start overhead; 60s completion timeout wasn't
    # enough for even a handful of tokens at ~10s/token on CPU-only
    # inference). Guards against a future "simplification" quietly
    # reintroducing either regression without re-measuring against real
    # hardware first.
    assert _AVAILABILITY_TIMEOUT_SECONDS >= 5.0
    assert _COMPLETION_TIMEOUT_SECONDS >= 120.0
