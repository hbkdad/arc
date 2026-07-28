# Contributing

## Setup

```bash
uv sync                 # install deps + local package into .venv
cp .env.example .env    # local dev data dir (repo-local ./data, gitignored)
uv run alembic upgrade head
uv run acr doctor
```

## Before opening a PR

Every change must pass the full quality gate:

```bash
uv run pytest            # tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # type check
```

## How this project is built

Read [`ACR_MASTER_SYSTEM_PROMPT.md`](ACR_MASTER_SYSTEM_PROMPT.md) first —
it's the full specification (roles, principles, architecture, milestone
order, security model) everything in this repo implements against.
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) tracks what actually exists
today versus that target, phase by phase, and is the authoritative source
for current status (nothing else in this repo should claim a status that
could drift out of sync with it).

Guiding rules that apply to any contribution, not just AI-assisted ones:

- Build the **smallest complete vertical slice** of one milestone at a
  time — never attempt the whole system in one change.
- Don't rewrite unrelated modules, remove working behavior without
  justification, or claim a feature works without running its tests.
- Default deny on permissions; no secrets in code, logs, or version
  control.
- No placeholder code that looks complete but isn't — if a stage is
  legitimately not implemented, report it as skipped/not-done, don't
  fake a passing result.

## Reporting bugs / requesting features

[GitHub Issues](https://github.com/hbkdad/arc/issues).

## Reporting security vulnerabilities

See [`SECURITY.md`](SECURITY.md) — please don't use a public issue for
these.
