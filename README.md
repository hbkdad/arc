# ACR: Adaptive Cognitive Runtime

[![CI](https://github.com/hbkdad/arc/actions/workflows/ci.yml/badge.svg)](https://github.com/hbkdad/arc/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/acr-runtime.svg)](https://pypi.org/project/acr-runtime/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[acr-runtime.netlify.app](https://acr-runtime.netlify.app/)

**A local-first AI orchestration runtime that runs entirely on your own
machine.** Persistent memory, a skill system, task/agent orchestration,
and multi-provider model routing, all on SQLite, with no cloud account,
API key, or telemetry required to try it. Point it at your own local
Ollama models when you want real inference, or keep it on the
zero-config mock provider indefinitely; ACR never assumes you're online
or paying for anything.

```bash
pip install acr-runtime
acr db upgrade && acr doctor
acr run "say hello"
```

Full specification: [`ACR_MASTER_SYSTEM_PROMPT.md`](ACR_MASTER_SYSTEM_PROMPT.md).
Current implementation state: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
the single source of truth for what's actually built, so nothing here
duplicates that status and drifts stale.

## What's here

A Python CLI (`acr`) built around a real task engine, a hybrid-retrieval
memory store, a skill registry with routing/validation/evolution, model
and tool routing with safe-mode-aware permission checks, an agent
planner/critic/topology system, an operational dashboard with a
real-telemetry visualization, and an MCP server exposing ACR's memory,
skill, web, and GitHub search tools to any MCP client, including
project-scoped registration for both Claude Code and Codex CLI out of
the box. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full
breakdown of what's implemented, how, and why.

## Quick start

Install from PyPI:

```bash
pip install acr-runtime   # or: uv tool install acr-runtime
acr db upgrade            # create the local SQLite schema, no repo checkout needed
acr doctor
```

Or from a source checkout (for development; see [`CONTRIBUTING.md`](CONTRIBUTING.md)):

```bash
uv sync                 # install deps + local package into .venv
cp .env.example .env    # local dev data dir (repo-local ./data, gitignored)
uv run alembic upgrade head
uv run acr doctor
```

```bash
acr run "say hello"          # create + execute a task end to end
acr dashboard serve          # operational dashboard: http://127.0.0.1:8765
acr mcp serve                # MCP server (stdio by default)
```
(prefix with `uv run` if working from a source checkout instead of a `pip`/`uv tool` install)

### Using ACR from Claude Code or Codex CLI

This repo ships project-scoped MCP server registration for both
[Claude Code](.mcp.json) and [Codex CLI](.codex/config.toml), so opening
it in either offers ACR's memory/skill/web/GitHub search tools and task
execution as MCP tools directly. Claude Code prompts for approval the
first time it opens the project; Codex CLI only loads project-scoped
config for a project you've marked trusted (`codex` trust prompt, or
`trust_level = "trusted"` under `[projects."<path>"]` in your own
`~/.codex/config.toml`); either way, cloning the repo can't silently
launch anything without you consenting.

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
