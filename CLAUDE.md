# CLAUDE.md

This repo builds **ACR — Adaptive Cognitive Runtime**, a local-first, model-independent AI orchestration runtime.

Full specification (roles, principles, architecture, milestones, security model, required report format):
→ [ACR_MASTER_SYSTEM_PROMPT.md](ACR_MASTER_SYSTEM_PROMPT.md)

Read it in full before any implementation work. Do not ask for a summary in place of reading it.

## Start every session with

[SESSION_TASK_PROMPT.md](SESSION_TASK_PROMPT.md)

## Non-negotiables (see master file for full list)

- Only build the **next incomplete milestone** (master §65–66). One smallest-complete vertical slice at a time — never the whole system in one session.
- Never rewrite unrelated modules, remove working behavior without justification, or claim a feature works without running its tests.
- Minimal context: don't load the whole repo, whole README, or full history into a task — retrieve only what's relevant (master §7–8).
- Default deny on permissions; no secrets in code, logs, memory, or Git (master §37–41).
- End every session with the **Required Session Report** (master §73): STATUS, IMPLEMENTED, FILES CHANGED, TESTS, TOKEN OPTIMIZATION, SECURITY, DECISIONS, NEXT STEP.

## Repo layout

Modular monorepo (master §5): `apps/`, `packages/`, `core/`, `memory/`, `context/`, `skills/`, `agents/`, `routing/`, `providers/`, `tools/`, `learning/`, `telemetry/`, `security/`, `benchmarks/`, `migrations/`, `tests/`, `scripts/`, `examples/`, `docs/`. Core domain logic must not depend on UI, provider implementations, or deployment platforms.

Today this lives as one `src/acr/` package with each domain as a submodule (`acr.memory`, `acr.agents`, ...) rather than literal top-level directories — a deliberate, revisit-when-needed choice, not drift; see [docs/adr/0001-src-layout-single-package.md](docs/adr/0001-src-layout-single-package.md). The dependency-direction rule still applies at the submodule level: nothing under `acr.core`/`acr.memory`/etc. may import a concrete provider adapter or `acr.dashboard`/`acr.cli` — only `acr.providers.base`'s abstract interface.
