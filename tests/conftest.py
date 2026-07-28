"""Shared pytest fixtures for the ACR test suite."""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Imported for side effects only: registers each domain's ORM tables on
# Base.metadata before any fixture calls Base.metadata.create_all().
from acr.agents import topology as _agent_topology_models  # noqa: F401
from acr.benchmarks import models as _benchmark_models  # noqa: F401
from acr.config import Settings, get_settings
from acr.core.tasks import models as _task_models  # noqa: F401
from acr.db.base import Base, make_engine, make_session_factory
from acr.memory import models as _memory_models  # noqa: F401
from acr.memory.fts import create_fts as create_memory_fts
from acr.skills import models as _skill_models  # noqa: F401
from acr.skills.fts import create_fts as create_skill_fts
from acr.telemetry import models as _telemetry_models  # noqa: F401


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point ACR at a fresh temp data dir so tests never touch a real ~/.acr or repo /data."""
    monkeypatch.setenv("ACR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ACR_LOG_FORMAT", "console")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.fixture
def settings(isolated_env: Path) -> Settings:
    return get_settings()


@pytest.fixture
async def migrated_settings(settings: Settings) -> AsyncIterator[Settings]:
    """`settings`, backed by a fresh SQLite file with all ORM tables created.

    Bypasses Alembic for test speed — Alembic remains the single source of
    truth for real deployments/migrations (see docs/ARCHITECTURE.md).
    """
    engine = make_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_memory_fts(conn)
        await create_skill_fts(conn)
    await engine.dispose()
    yield settings


@pytest.fixture
async def db_session(migrated_settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = make_engine(migrated_settings)
    factory = make_session_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()


class _FixedPageHandler(BaseHTTPRequestHandler):
    """Serves a single, fixed HTML body — enough for web_fetch call sites
    that only need *a* real HTTP response, not specific routing."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><h1>Hello</h1><p>local test page</p></body></html>")

    def log_message(self, format: str, *args: object) -> None:
        pass  # silence request logging during tests


@pytest.fixture
def local_html_server() -> Iterator[str]:
    """Base URL of a real, ephemeral, localhost-only HTTP server."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FixedPageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
