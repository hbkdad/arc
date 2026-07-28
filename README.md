# ACR — Adaptive Cognitive Runtime

[![CI](https://github.com/hbkdad/arc/actions/workflows/ci.yml/badge.svg)](https://github.com/hbkdad/arc/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Local-first, model-independent AI orchestration and cognitive runtime.
Full specification: [`ACR_MASTER_SYSTEM_PROMPT.md`](ACR_MASTER_SYSTEM_PROMPT.md).
Current state and toolchain: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
— that document is the single source of truth for exactly what phase this
repo is at; nothing here duplicates that status so it can't drift stale.

## What's here

A Python CLI (`acr`) built around a real task engine, a hybrid-retrieval
memory store, a skill registry with routing/validation/evolution, model
and tool routing with safe-mode-aware permission checks, an agent
planner/critic/topology system, an operational dashboard with a
real-telemetry visualization, and an MCP server exposing ACR's memory,
skill, web, and GitHub search tools to any MCP client. Runs entirely on
SQLite with a zero-config mock model provider by default — no cloud
account or API key required to try it. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full breakdown of
what's implemented, how, and why.

## Quick start

```bash
uv sync                 # install deps + local package into .venv
cp .env.example .env    # local dev data dir (repo-local ./data, gitignored)
uv run alembic upgrade head
uv run acr doctor
```

```bash
uv run acr run "say hello"          # create + execute a task end to end
uv run acr dashboard serve          # operational dashboard: http://127.0.0.1:8765
uv run acr mcp serve                # MCP server (stdio by default)
```

## Development

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full workflow. Short version:

```bash
uv run pytest            # tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # type check
```

## License, security, support

[MIT licensed](LICENSE). See [`SECURITY.md`](SECURITY.md) to report a
vulnerability privately. For bugs, questions, or feature requests, use
[GitHub Issues](https://github.com/hbkdad/arc/issues).
