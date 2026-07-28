# ACR — Adaptive Cognitive Runtime

Local-first, model-independent AI orchestration and cognitive runtime.
Full specification: [`ACR_MASTER_SYSTEM_PROMPT.md`](ACR_MASTER_SYSTEM_PROMPT.md).
Current state and toolchain: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Quick start

```bash
uv sync                 # install deps + local package into .venv
cp .env.example .env    # local dev data dir (repo-local ./data, gitignored)
uv run alembic upgrade head
uv run acr doctor
```

## Development

```bash
uv run pytest           # tests
uv run ruff check .     # lint
uv run ruff format .    # format
uv run pyright          # type check
```

Status: **Phase 0 — Foundation** (see `docs/ARCHITECTURE.md`).
