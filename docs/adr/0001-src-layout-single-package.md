# ADR-0001: `src/acr/` single package, not the literal multi-directory monorepo tree yet

## Status

Accepted — Phase 0 (Foundation).

## Context

The master spec (§5) defines a modular monorepo with `core/`, `memory/`,
`context/`, `skills/`, `agents/`, `routing/`, `providers/`, `tools/`,
`learning/`, `telemetry/`, `security/`, etc. as top-level sibling directories
of `apps/` and `packages/`. That tree describes ACR's eventual shape, once
`apps/dashboard`, `apps/website`, and `apps/desktop` exist as real, separately
deployed applications that need their own dependency graphs.

At Phase 0, exactly one deployable thing exists: a Python CLI. Creating a
dozen top-level directories today, each empty except for an `__init__.py`,
would be scaffolding with no behavior behind it — the kind of "placeholder
code that appears complete" the master spec explicitly warns against (§309),
and unnecessary infrastructure (principle #24).

## Decision

Use a single, standard **src-layout** Python package: `src/acr/`, built with
`uv` and its native `uv_build` backend. Domain modules are named to mirror
the master spec's architecture (`acr.db`, `acr.config`, `acr.cli`, and later
`acr.memory`, `acr.context`, `acr.skills`, `acr.agents`, `acr.routing`,
`acr.providers`, `acr.tools`, `acr.learning`, `acr.telemetry`, `acr.security`)
so each maps 1:1 to a future top-level directory.

Dependency direction is enforced the same way regardless of nesting depth:
domain modules (`acr.memory`, `acr.core`, ...) must not import from
`acr.cli` or any future `apps/*`.

## Consequences

- Fast to stand up, fully testable via `uv run pytest` today.
- When a module's code and test surface grow large enough, or when it needs
  independent versioning/packaging (e.g. shipped as its own library), split
  it out to a top-level directory and register it as a `uv` workspace member
  — a mechanical move, not a redesign.
- `apps/dashboard`, `apps/website`, `apps/desktop` are not created until
  their phases (11, 14, 51) actually need them.

## Update (2026-08-01): Phase 11 landed, and this decision held

Phase 11 (Dashboard) is complete, and its trigger condition here — "once
`apps/dashboard`... exist as real, separately deployed applications that
need their own dependency graphs" — never actually fired: the dashboard
is a FastAPI app served by `acr dashboard serve`, sharing the CLI's own
process/dependency graph, not a separately deployed application. It
landed as `acr.dashboard`, a submodule alongside `acr.cli`, exactly the
pattern this ADR already described rather than a new `apps/dashboard`.
This ADR's own prediction turned out correct, not just untested.

One real exception this ADR didn't originally account for: `skills/`
now exists at the repo root, alongside `src/`, holding ACR's first-party
skill *packages* (`SKILL.yaml` + `instructions.md` content, not Python
code) — `code-review-checklist`, `context-minimization`,
`dashboard-design-elaborate`, `dashboard-ui-audit`, `ui-design-critique`.
This doesn't contradict the single-package decision above (it's data
`acr.skills.registry.register()` reads, not a second Python package,
and the "Domain modules... map 1:1 to a future top-level directory"
mapping above is unaffected) — see `docs/ARCHITECTURE.md`'s "First-party
skill library" section for the full rationale. Noted here so a reader
following this ADR alone doesn't come away thinking no top-level
directory exists yet.

## Revisit when

A second deployable Python app needs to share `acr.core`/`acr.memory` code,
or any domain module's dependency footprint diverges enough from the CLI's
that they should not share one `pyproject.toml`.
