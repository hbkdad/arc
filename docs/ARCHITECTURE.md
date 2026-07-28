# ACR Architecture

Full specification: [`ACR_MASTER_SYSTEM_PROMPT.md`](../ACR_MASTER_SYSTEM_PROMPT.md).
This document tracks what actually exists, versus what the master spec
describes as the eventual target.

## Target shape (master §5)

A modular monorepo: `apps/` (api, dashboard, website, desktop), `packages/`
(shared UI, viz, client-sdk, types), and domain directories (`core/`,
`memory/`, `context/`, `skills/`, `agents/`, `routing/`, `providers/`,
`tools/`, `learning/`, `telemetry/`, `security/`), plus `benchmarks/`,
`migrations/`, `tests/`, `scripts/`, `examples/`, `docs/`.

## Current shape (Phase 0 Foundation + Phase 1 Execution)

Only the Python CLI foundation and task engine exist. See
[`docs/adr/0001-src-layout-single-package.md`](adr/0001-src-layout-single-package.md)
for why this is one `src/acr/` package rather than the full multi-directory
tree, and when to split it.

```
acrtest/
├── pyproject.toml         # uv project: deps, ruff, pyright, pytest config
├── uv.lock
├── alembic.ini
├── migrations/            # Alembic (async), env.py reads acr.config.Settings
│   ├── env.py
│   └── versions/
│       ├── 0dd629888bfd_baseline.py
│       └── 87b619c4e7ac_task_engine_and_telemetry_tables.py
├── src/acr/
│   ├── __init__.py        # __version__
│   ├── config.py          # Settings (pydantic-settings, ACR_* env / .env)
│   ├── logging.py         # structlog JSON/console setup
│   ├── db/
│   │   ├── __init__.py
│   │   └── base.py        # async SQLAlchemy engine/session, Base
│   ├── doctor.py          # health checks used by `acr doctor`
│   ├── cli.py             # Typer app: `acr version`, `acr doctor`, `acr run`
│   ├── core/
│   │   ├── tasks/models.py       # Task, TaskRun, Step, TaskStatus + lifecycle rules
│   │   └── execution/engine.py   # run_task(): drives a Task through a provider
│   ├── providers/
│   │   ├── base.py        # ModelProvider ABC (provider-independence boundary)
│   │   ├── mock.py         # MockProvider — zero-config default, no network
│   │   └── ollama.py       # OllamaProvider — optional local HTTP adapter
│   └── telemetry/
│       ├── models.py       # TelemetryEvent
│       └── recorder.py     # TelemetryRecorder.emit() — DB + structured log
├── tests/
│   ├── conftest.py         # isolated_env / settings / migrated_settings / db_session
│   ├── test_config.py
│   ├── test_doctor.py
│   ├── test_cli.py
│   ├── test_task_lifecycle.py
│   ├── test_providers.py
│   └── test_execution_engine.py
└── docs/
    ├── ARCHITECTURE.md     # this file
    └── adr/0001-src-layout-single-package.md
```

## Toolchain (master §116, verified current in 2026-07)

- **uv** — Python install, venv, dependency resolution/locking, running
  scripts. Native `uv_build` backend (no setuptools/hatchling needed).
- **Ruff** — lint + format (replaces flake8/black/isort).
- **Pyright** — static type checking, `standard` mode.
- **pytest** (+ `pytest-asyncio`, `asyncio_mode = "auto"`) — tests.
- **Typer** — CLI framework (Click-based, first-class type hints).
- **pydantic-settings** — typed, env-driven configuration.
- **SQLAlchemy 2.0 (async) + aiosqlite** — local SQLite persistence.
- **Alembic** (async template) — schema migrations, URL sourced from
  `acr.config.Settings.database_url` — never hardcoded in `alembic.ini`.
- **structlog** — structured JSON logging (console mode for local dev).
- **httpx** — async HTTP client, used only by `OllamaProvider` (localhost only).

## Local-first data

Default data directory: `~/.acr` (`acr.config.Settings.data_dir`), containing
`acr.db` (SQLite). Override with `ACR_DATA_DIR` (see `.env.example`). Local
development uses a repo-local `./data/` (gitignored) via `.env` so `acr
doctor` / tests never touch a real user's home directory.

## Task engine (Phase 1)

`acr.core.execution.run_task()` is the smallest complete slice of master
§948-976: it creates a `Task`, drives it through one `TaskRun` against a
`ModelProvider` (`CREATED -> PLANNING -> EXECUTING -> VERIFYING ->
COMPLETED`, or `FAILED` if the provider call raises), recording `Step`s and
telemetry events at every transition. Multi-step planning, retries, and
resource budgets are not yet implemented — they land only once a real task
needs them (avoids speculative infrastructure, master principle #24).

`acr.providers.base.ModelProvider` is the one seam core code is allowed to
depend on for "call a model" — never a specific SDK. `MockProvider` (no
network, deterministic) is the CLI's default so `acr run` works with zero
configuration. `OllamaProvider` talks only to `localhost:11434`; it exists as
infrastructure but isn't the default yet — real provider routing (prefer
local, escalate to cloud on verification failure) is master §794-813, Phase 6.

## Commands available today

```bash
uv run acr doctor          # Python version, data dir, DB, mock + Ollama providers
uv run acr version
uv run acr run "objective" # create + execute a Task end-to-end via the mock provider
uv run alembic upgrade head
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

## Next milestone

Phase 2 — Memory: memory schema, SQLite FTS5 retrieval, temporal memory,
failure memory, write controller (master §473-576).
