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

## Current shape (all 15 master-spec phases: Phase 0 Foundation through Phase 15 Controlled Self-Improvement)

Every phase in the master spec's §65-66 milestone list now has at least a
smallest-complete-vertical-slice implementation: task engine, memory
system, context compiler, skill system, evaluation system, model/tool
routing, security layer, learning system, skill validation/evolution,
agents, the operational dashboard, a real-telemetry visualization, an MCP
server, web-fetch/browser/GitHub-search tools, baseline OSS repo hygiene,
and controlled self-improvement proposals. This does **not** mean the
system is "done" — see each phase's section below for exactly what's
real versus deliberately deferred (a desktop app, a PyPI package, and
several Phase 15 sub-bullets remain explicitly out of scope). See
[`docs/adr/0001-src-layout-single-package.md`](adr/0001-src-layout-single-package.md)
for why this is one `src/acr/` package rather than the full multi-directory
tree, and when to split it.

```
acrtest/
├── README.md
├── LICENSE                # MIT
├── SECURITY.md            # GitHub private vulnerability reporting
├── CONTRIBUTING.md
├── .mcp.json               # registers `acr mcp serve` as a Claude Code project MCP server
├── .codex/config.toml      # same, for Codex CLI (loaded only for trusted projects)
├── .github/workflows/ci.yml       # ruff + pyright + migrations + pytest, every push/PR
├── .github/workflows/publish.yml  # PyPI Trusted Publishing, on GitHub Release
├── pyproject.toml         # uv project: deps, ruff, pyright, pytest config
├── uv.lock
├── alembic.ini             # script_location = src/acr/migrations (dev/source-checkout path)
├── src/acr/
│   ├── __init__.py        # __version__
│   ├── config.py          # Settings (pydantic-settings, ACR_* env / .env)
│   ├── logging.py         # structlog JSON/console setup
│   ├── migrations/        # Alembic (async) -- lives *inside* the package so it ships
│   │   ├── env.py         # in the wheel; alembic.ini points here for the dev path too
│   │   └── versions/
│   │       ├── 0dd629888bfd_baseline.py
│   │       ├── 87b619c4e7ac_task_engine_and_telemetry_tables.py
│   │       ├── 6c384104b66a_memory_records_and_fts5.py
│   │       ├── 83b4d32aa8f2_skills_registry_and_fts5.py
│   │       ├── 5a8d4f37fff6_benchmark_runs.py
│   │       ├── 90f73bb6afb3_agent_topology_records.py
│   │       ├── ac998e062cab_hot_path_indexes.py
│   │       └── f0aa4f554248_self_improvement_proposals.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py        # async SQLAlchemy engine/session, Base
│   │   └── migrate.py     # upgrade_to_head(): programmatic Alembic, no alembic.ini needed
│   ├── doctor.py          # health checks used by `acr doctor`
│   ├── cli.py             # Typer app: version/doctor/run/context/skills
│   ├── core/
│   │   ├── tokens.py              # shared estimate_tokens()
│   │   ├── fts_query.py           # shared FTS5 MATCH query builder (OR + stopwords)
│   │   ├── tasks/models.py       # Task, TaskRun, Step, TaskStatus + lifecycle rules
│   │   └── execution/engine.py   # run_task(): drives a Task through a provider
│   ├── providers/
│   │   ├── base.py        # ModelProvider ABC (provider-independence boundary)
│   │   ├── mock.py         # MockProvider — zero-config default, no network
│   │   ├── ollama.py       # OllamaProvider — local HTTP adapter + list_models()
│   │   ├── openai_compatible.py     # OpenAICompatibleProvider — opt-in, needs an API key
│   │   └── anthropic_compatible.py  # AnthropicCompatibleProvider — opt-in, needs an API key
│   ├── telemetry/
│   │   ├── models.py       # TelemetryEvent
│   │   └── recorder.py     # TelemetryRecorder.emit() — DB + structured log
│   ├── memory/
│   │   ├── models.py         # MemoryRecord + Type/Scope/Status enums
│   │   ├── fts.py            # FTS5 virtual table + sync triggers (shared: migration + tests)
│   │   ├── retrieval.py       # hybrid retrieval: FTS + metadata + ranking + token budget
│   │   ├── temporal.py        # current() / at() / history()
│   │   └── write_controller.py  # evaluate()/apply()/remember() decision policy
│   ├── context/
│   │   ├── models.py         # ContextItem, ContextBundle
│   │   ├── compiler.py        # compile_context(): discover->...->assemble pipeline
│   │   └── attribution.py     # record_attribution(): feeds usage back into memory utility
│   ├── skills/
│   │   ├── format.py         # SKILL.yaml manifest schema + loader
│   │   ├── models.py          # SkillRecord + SkillStatus lifecycle rules
│   │   ├── fts.py             # skills_fts virtual table + sync triggers
│   │   ├── registry.py        # register()/get()/list_skills()/set_status()
│   │   ├── search.py          # FTS keyword search over the registry
│   │   ├── routing.py         # route(): the master §685-696 8-step process
│   │   ├── validation.py      # run_validation(): the master §717-731 pipeline
│   │   └── evolution.py       # versioned candidates, compare/promote/rollback
│   ├── evaluation/
│   │   ├── models.py          # EvaluationCriterion, CriterionScore, EvaluationResult
│   │   ├── evaluators.py       # Evaluator ABC, ChecklistEvaluator, ExactMatchEvaluator
│   │   ├── panel.py            # evaluate_with_panel(): majority-vote aggregation
│   │   ├── regression.py       # detect_regression(): compare consecutive BenchmarkRuns
│   │   └── waste_analyzer.py   # duplicate-memory + context-utilization detectors
│   ├── benchmarks/
│   │   ├── models.py          # BenchmarkCase/CaseResult (in-memory), BenchmarkRun (persisted)
│   │   ├── runner.py           # run_suite(): executes cases for real, persists a BenchmarkRun
│   │   └── memory_recall.py    # a genuine memory-recall suite exercising Phase 2 code
│   ├── routing/
│   │   └── models.py          # ModelProfile/ModelRouter: cheapest-qualified + escalation
│   ├── tools/
│   │   ├── models.py          # ToolSpec (master §827-838 field set), SideEffectLevel
│   │   ├── registry.py        # in-memory ToolRegistry (tools are code, not user data)
│   │   ├── default_tools.py    # real tools: memory_search, skill_search, web_fetch
│   │   ├── web_fetch.py        # http(s) GET + stdlib HTML text extraction, injection-scanned
│   │   ├── browser.py          # real (Playwright) headless-browser render + text extraction
│   │   ├── github_search.py    # read-only issue/PR search via the already-authenticated gh CLI
│   │   ├── exposure.py         # expose_tools(): task-specific subset, min-relevance gated
│   │   └── invocation.py       # invoke_tool(): permission + safe-mode check, audit-logged
│   ├── security/
│   │   ├── permissions.py     # Capability enum, default-deny PermissionSet
│   │   ├── trust.py            # TrustLevel, combine_trust() (minimum of the chain)
│   │   ├── injection.py        # scan_for_injection(): deterministic heuristic scanner
│   │   ├── secrets.py          # redact_secrets()/redact_mapping() — wired into telemetry
│   │   ├── sandbox.py          # SandboxPolicy, build_sandboxed_env() (env allowlist + redact)
│   │   ├── safe_mode.py        # SafeModeError, require_not_safe_mode()
│   │   └── audit.py            # record_audit_event()/recent_audit_events() (via telemetry)
│   ├── learning/
│   │   ├── distillation.py     # distill_task()/distill_and_remember(): trace -> memory candidate
│   │   ├── utility.py          # record_skill_outcome(): SkillRecord successful_uses/reliability
│   │   ├── promotion.py        # promote_candidates(): CANDIDATE -> CONFIRMED on earned utility
│   │   ├── skill_generation.py # detect_repeated_successes()/generate_candidate_skill()
│   │   └── proposals.py        # Proposal: evidence-backed, approval-gated self-improvement
│   ├── agents/
│   │   ├── models.py           # AgentSpec (master §749-763 field set), SpawnEstimate
│   │   ├── factory.py          # estimate_spawn()/spawn_agent(): cost/value gate, runs via run_task()
│   │   ├── planner.py          # plan_agent(): real skill routing + tool exposure for a spec
│   │   ├── critic.py           # review_agent_task(): reuses Phase 5's evaluation panel
│   │   └── topology.py         # AgentTopologyRecord, record_topology()/recommend_topology()
│   ├── dashboard/
│   │   ├── queries.py          # read-only SELECTs backing every dashboard/visualization view
│   │   ├── app.py              # create_app(): FastAPI + Jinja2, one route per operational view
│   │   ├── templates/          # base.html + one template per view, plain tables, no JS framework
│   │   └── static/
│   │       └── visualization.js  # hand-written Canvas2D scene, polls /api/graph, no library
│   └── integrations/
│       └── mcp_server.py       # create_mcp_server(): memory_search/skill_search/run_task over MCP
├── tests/
│   ├── fixtures/skills/       # sqlite-diagnostics (valid), broken-skill (invalid manifest)
│   ├── conftest.py         # isolated_env / settings / migrated_settings / db_session
│   ├── test_config.py
│   ├── test_doctor.py
│   ├── test_cli.py
│   ├── test_task_lifecycle.py
│   ├── test_providers.py
│   ├── test_execution_engine.py
│   ├── test_core_tokens.py
│   ├── test_core_fts_query.py
│   ├── test_memory_models.py
│   ├── test_memory_write_controller.py
│   ├── test_memory_temporal.py
│   ├── test_memory_retrieval.py
│   ├── test_context_compiler.py
│   ├── test_context_attribution.py
│   ├── test_skill_format.py
│   ├── test_skill_registry.py
│   ├── test_skill_search.py
│   ├── test_skill_routing.py
│   ├── test_evaluation.py
│   ├── test_benchmarks.py
│   ├── test_regression.py
│   ├── test_waste_analyzer.py
│   ├── test_providers_cloud.py
│   ├── test_model_router.py
│   ├── test_tools.py
│   ├── test_security_permissions.py
│   ├── test_security_trust.py
│   ├── test_security_injection.py
│   ├── test_security_secrets.py
│   ├── test_security_sandbox.py
│   ├── test_security_safe_mode.py
│   ├── test_security_audit.py
│   ├── test_tools_invocation.py
│   ├── test_learning_distillation.py
│   ├── test_learning_utility.py
│   ├── test_learning_promotion.py
│   ├── test_learning_skill_generation.py
│   ├── test_learning_proposals.py
│   ├── test_skill_validation.py
│   ├── test_skill_evolution.py
│   ├── test_agents_factory.py
│   ├── test_agents_planner_critic.py
│   ├── test_agents_topology.py
│   ├── test_dashboard.py
│   ├── test_mcp_server.py
│   ├── test_tools_web_fetch.py
│   ├── test_tools_github_search.py
│   └── test_tools_browser.py
└── docs/
    ├── ARCHITECTURE.md     # this file
    └── adr/0001-src-layout-single-package.md
```

## Reference material (not part of this repo)

`https://github.com/hbkdad/Adaptive-Cognitive-Runtime` is the user's own,
much more mature implementation of this same master spec (~53k lines, 81
modules, 76 test files, ~73/131 of its own finer-grained prompt breakdown
complete as of 2026-07-28). It deliberately chose the opposite architecture
(pure standard library — no FastAPI/Pydantic/ORM — see its ADR-0001) from
this repo's uv+SQLAlchemy+Pydantic+FastAPI stack. Per explicit user decision,
this repo (`acrtest`) stays independent: that repo is read-only reference for
design ideas, never a source to port code from, and is never committed or
pushed to from here.

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
- **FastAPI + Jinja2 + uvicorn** — the operational dashboard (Phase 11):
  server-rendered HTML, no separate frontend build step.
- **mcp** (the official Model Context Protocol Python SDK) — the MCP
  server (Phase 13a). Supports stdio/SSE/streamable-HTTP transports.
- **playwright** — real headless-browser automation (Phase 13). The
  browser binary itself (`playwright install chromium`) is a distinct,
  separately-confirmed action, never triggered as a side effect of
  installing the Python package.
- **gh CLI** (external, not a Python dependency) — GitHub search (Phase
  13c). Owns its own authentication entirely; ACR's code never sees a
  GitHub token.

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
configuration. `OllamaProvider` talks only to `localhost:11434`. Real
provider routing (prefer local, escalate to cloud on verification failure)
is `acr.routing.models` — see Phase 6 below, and "Real provider routing"
further down for how `acr run`/MCP `run_task` actually reach it now.

## Memory system (Phase 2)

`acr.memory.models.MemoryRecord` is one unified, typed table (master
§473-529) rather than one table per `MemoryType` — failure memory (§615-629)
is `MemoryType.FAILURE` with its task-class/symptom/root-cause fields in
`structured_payload`, not a bespoke table. `write_controller.evaluate()` is a
deterministic v1 policy (no LLM yet — see module docstring for why) covering
all eight decisions from §566-574; `retrieval.retrieve()` implements the
hybrid pipeline from §530-551 (SQLite FTS5 keyword search + scope/type/status/
temporal filtering + confidence/importance/utility ranking + token-budgeted
selection with explanations); `temporal.py` implements `current()`/`at()`/
`history()` per §577-591, preserving old records via `supersedes`/
`superseded_by` rather than deleting them. Semantic (embedding) similarity is
deliberately not implemented — the Phase 2 milestone calls out "FTS
retrieval", not semantic, and adding an embeddings model now would be
infrastructure ahead of evidence it's needed.

FTS5 `MATCH` ANDs bare terms by default, so `retrieve()` builds an OR-joined,
quoted, stopword-filtered query (`acr.core.fts_query.build_match_query`,
shared with skill search — see Phase 4 below) — passing a full
natural-language task objective straight through as an implicit AND would
only match content containing *every single word* of it.

## Context compiler (Phase 3)

`acr.context.compiler.compile_context()` runs the master §411-450 pipeline —
DISCOVER (over-fetch from `memory.retrieve()`) -> FILTER/RANK (inherited from
retrieval) -> DEDUPLICATE (by exact content) -> VALIDATE -> RESOLVE TEMPORAL
CONFLICTS (a no-op today: retrieval already restricts to current records) ->
EXPAND REQUIRED DEPENDENCIES (a no-op: no dependency graph exists yet) ->
COMPRESS (deterministic truncation past 2000 chars, no LLM) -> ESTIMATE
TOKENS (`acr.core.tokens`) -> OPTIMIZE (greedy knapsack by relevance/token) ->
ASSEMBLE into a `ContextBundle`. Memory is the only real context source;
`selected_skills`/`selected_tools`/`selected_code`/`selected_documents` are
real fields on the bundle that stay empty until Phases 4-6/13 exist.

`acr.context.attribution.record_attribution()` closes the loop master §463
asks for: given which bundle item IDs a task actually used, it increments
each source record's `successful_uses`/`failed_uses` and recomputes
`utility_score` — which is exactly what `retrieval.retrieve()`'s ranking
already reads. Items that were offered but not used are left untouched
(§464-465: not used ≠ useless). Skills aren't wired into the compiler yet
(the bundle has no skill items to attribute), so `SkillRecord.successful_uses`/
`failed_uses` (Phase 4 below) aren't updated by attribution today either.
`record_attribution()` optionally takes a `TelemetryRecorder` + `task_id` and
emits a `context.attribution` event (bundle/referenced token counts) — this
is what Phase 5's waste analyzer reads to report context utilization.

## Skill system (Phase 4)

A skill package is a directory containing `SKILL.yaml` (required — parsed by
`acr.skills.format.load_manifest` into a validated `SkillManifest`, master
§655-676's exact required field set) and optionally `instructions.md`. The
`skills` table is a metadata-only registry populated by
`registry.register()` — a query never re-reads the package's files off disk
(master §683: "discoverable without loading every skill into context").
Re-registering an already-registered skill (same manifest `id`) updates its
metadata but preserves `status`/`reliability`/use counters — activation
state is earned, not reset by re-reading a file.

Lifecycle (master §679-682) is validated the same way `Task`'s is (Phase 1):
`experimental -> {quarantined, active}`, `quarantined -> {active, retired}`,
`active -> {deprecated, quarantined}`, `deprecated -> {retired, active}`,
`retired` terminal. Only `active` skills are ever routed to.

`routing.route()` implements the master §685-696 8-step process: classify
(caller-supplied `task_class`, no classifier model yet) -> retrieve
candidates (**every** active skill — keyword search supplies a relevance
signal but never gates candidacy, so a `task_class` match surfaces a skill
even with zero keyword overlap with the task description) -> estimate
applicability (max of keyword relevance and an exact task_class match) ->
estimate expected quality gain (applicability weighted by `reliability`,
which doubles as step 6's "check prior performance" — it *is* the
successful/total ratio a skill has earned) -> estimate token overhead
(`token_estimate`) -> remove overlapping skills (drop a candidate whose
`task_classes` are a subset of an already-kept, higher-scoring candidate's)
-> return the top `max_skills`.

### First-party skill library (2026-07-29)

`skills/` (repo root, alongside `tests/fixtures/skills/`'s test-only
fixtures) holds ACR's actual, registered-and-active skill packages —
`dashboard-ui-audit`, `ui-design-critique`, `code-review-checklist`,
`context-minimization`. Each declares only tools/permissions ACR's real
registries have (`acr.tools.default_tools.build_default_registry()`,
`acr.security.permissions.Capability`) — `acr skills register` doesn't
validate at registration time, so a manifest referencing a since-renamed
capability or a tool that doesn't exist would otherwise fail silently
until someone happened to run `acr skills validate --check-tools` by
hand. `tests/test_real_skills.py` parametrizes over every directory under
`skills/`, registers it, and asserts `run_validation(..., tool_registry=
build_default_registry())` passes — a regression guard against exactly
that drift, not just a fixture-only validation test.

These four were written, not ported wholesale from Claude Code's own
~200-skill library: most of those are tied to connectors ACR doesn't have
(Figma, Slack, Zapier, ...), and registering a skill declaring a tool ACR
can't actually invoke would be a false capability claim in its own skill
registry — the opposite of the evidence-based design memory/skills were
built around (master principle #22). Only tool-agnostic, generically
applicable methodology made the cut.

## Evaluation system (Phase 5)

`acr.evaluation.evaluators.Evaluator` is the interface every evaluator
implements. `ChecklistEvaluator`/`ExactMatchEvaluator` are fully
deterministic (master §1515: no paid model access required for the normal
test suite) — an LLM-judge evaluator is a future `Evaluator` implementation,
not a different interface. `panel.evaluate_with_panel()` runs every
evaluator independently and aggregates by majority vote (master §1059: "Do
not use one model's confidence as ground truth").

`acr.benchmarks` cases are real, executable code, not fixture data with a
hardcoded expected score — `memory_recall.py` seeds actual facts through
`write_controller.remember()` and checks whether `retrieval.retrieve()`
actually surfaces them (master §1090: never publish a fabricated result).
`runner.run_suite()` persists one `BenchmarkRun` row per execution;
`evaluation.regression.detect_regression()` compares the two most recent
runs of a suite and flags a score drop past a threshold — a single run in
isolation has no opinion about regression.

`evaluation.waste_analyzer` has two detectors grounded in data ACR actually
has: `find_duplicate_memories()` (byte-identical memory content stored under
different subjects — `write_controller` already prevents duplicates *within*
one subject/scope/type) and `analyze_context_utilization()` (aggregates
`context.attribution` telemetry into a referenced/compiled token ratio). The
other master §1026-1039 waste categories (oversized system prompts, unused
tool/skill definitions, excessive agent coordination) need subsystems that
don't exist yet and are deliberately not stubbed.

## Model and tool routing (Phase 6)

`acr.routing.models.ModelRouter` implements master §805-806's routing
objective (cheapest model expected to meet a quality threshold) and
§807-812's escalation (try the cheapest qualifying model; if a caller's
`verify` rejects the result, escalate to the next-higher-`quality_tier`
available model; return which models were tried so escalation's effect is
trackable rather than invisible). `build_default_router()` wires the
standard ladder: `mock` (tier 0, free, always available) -> `ollama` (tier
1, free, available iff reachable) -> `openai_compatible`/
`anthropic_compatible` (tier 2, paid, available iff an API key is
configured via `ACR_OPENAI_API_KEY`/`ACR_ANTHROPIC_API_KEY` — master
principle #2: cloud-optional). `OllamaProvider.list_models()` is master
§814-824's "detect local Ollama models", hitting `/api/tags` for real.

`acr.tools` is a new domain: `ToolSpec` carries the exact field set master
§827-838 requires (schemas, permissions, `SideEffectLevel`, cost/latency
estimates, network/filesystem access, credential requirements). Tools are
code-registered, not user-submitted data like memories or skills — there's
no "generate a tool at runtime" concept in the master spec — so
`ToolRegistry` is in-memory, not a DB table. `default_tools.py` registers
two real tools (`memory_search`, `skill_search`) wrapping Phase 2/4 code, so
the registry demonstrates actual invocation, not just metadata bookkeeping.
`exposure.expose_tools()` is master §843-844's "tool exposure must be
task-specific... do not load every tool definition into every model call":
keyword-relevance ranked, gated by a minimum-relevance threshold so a
single word two tools happen to share (e.g. both being "search" tools)
isn't enough to expose an otherwise-irrelevant one — a real gap this
phase's own tests found.

## Security (Phase 7)

`acr.security.permissions.PermissionSet` is default-deny: nothing is
granted unless explicitly constructed with capabilities, and an
unrecognized capability string denies rather than crashing (a real gap this
phase's own tests found — `Capability("skill.read")`-style string coercion
would otherwise raise an uncaught `ValueError`). `acr.security.trust`
implements master §1122-1130's five trust levels and `combine_trust()`,
which takes the *minimum* of its inputs — a chain is only as trusted as its
weakest link. `memory_trust_level()` maps a `MemoryRecord`'s status
directly onto trust: only `CONFIRMED` reaches `VERIFIED_MEMORY`,
`QUARANTINED` (no evidence) is `UNTRUSTED`, everything else is
`RETRIEVED_CONTENT`. `acr.security.injection.scan_for_injection()` is a
deterministic heuristic over untrusted text — it flags, it never silently
blocks or trusts (master §1150-1166).

`acr.security.secrets.redact_mapping()` is wired directly into
`acr.telemetry.recorder.TelemetryRecorder.emit()` — every persisted/logged
event payload passes through it first (master §1024/§1191). `sandbox.py`'s
`SandboxPolicy` + `build_sandboxed_env()` are real and testable today even
though ACR has no code-execution engine yet to sandbox (skills are metadata
+ instructions, not executable code until Phase 9) — an env-var allowlist
filter + secret redaction, ready for whatever executes untrusted code
first.

Safe mode (`Settings.safe_mode`, `ACR_SAFE_MODE`) and audit logging (reuses
`TelemetryEvent` — a `security.audit` event is a telemetry event like any
other, not a parallel logging system) are wired into the two real mutating
operations ACR has: `skills.registry.set_status()` blocks activation
(`SafeModeError`) when safe mode is on, and `tools.invocation.invoke_tool()`
checks both a tool's declared `permissions` against the caller's grants and
(for non-`READ_ONLY` tools) safe mode, audit-logging every call — granted
or denied.

## Learning (Phase 8)

`acr.learning.distillation.distill_task()` converts one completed Task's
raw trace (its `TaskRun`s and `Step`s — Phase 1) into a compact `episodic`
memory candidate, reporting the compression ratio achieved (master §644).
Raw traces are never touched or duplicated — they stay exactly where Phase
1 put them (`tasks`/`task_runs`/`steps`), "outside normal context" (§642):
the context compiler (Phase 3) only ever reads `memory_records`. A task
that didn't complete yields no candidate — a "lesson" from an unfinished
task would be exactly the unevidenced claim master principle #22 forbids.
`distill_and_remember()` hands the candidate to the write controller
(Phase 2) rather than granting itself confirmed memory.

`acr.learning.utility.record_skill_outcome()` closes a real Phase 4 gap:
`SkillRecord.successful_uses`/`failed_uses`/`reliability` existed as
columns from the start, but nothing ever wrote to them, so
`routing.route()`'s "check prior performance" step always saw `0.0`. This
mirrors the same pattern `context.attribution` already established for
memory.

`acr.learning.promotion.promote_candidates()` is master §592-601's
"promote useful patterns": a `CANDIDATE` memory graduates to `CONFIRMED`
once `utility_score` and `successful_uses` (both already maintained by
`context.attribution`) clear configurable thresholds. Promotion also raises
the record's trust level — Phase 7's `memory_trust_level()` maps
`CONFIRMED` to `VERIFIED_MEMORY` — so this is the actual mechanism by which
a memory earns higher trust over time, not just a status flip.

`acr.learning.skill_generation` implements master §697-716: detects task
objectives that have completed successfully at least `min_repeats` times
(`detect_repeated_successes()`), then `generate_candidate_skill()` writes a
*real* `SKILL.yaml` package under `<data_dir>/generated_skills/<id>/`,
registers it through the normal `acr.skills.registry.register()` path, and
explicitly quarantines it (master §704: "Generated skills begin in
quarantine") — never active, never trusted until Phase 9's validation
pipeline exists. Generation is idempotent and safe to re-run: it never
re-quarantines a skill that a human has already reviewed and activated (a
real bug this phase's own tests caught — the naive version crashed trying
to re-transition an already-quarantined skill on a second run).

## Skill validation and evolution (Phase 9)

`acr.skills.validation.run_validation()` runs the master §717-731 pipeline:
schema validation (re-parses `SKILL.yaml` — catches *drift*, since
`register()` already requires a valid manifest to create a `SkillRecord` at
all) -> dependency check (declared `tools` against a supplied
`ToolRegistry`, Phase 6) -> static security scan (`scan_for_injection()`
over description/applicability/instructions.md, Phase 7) -> permission
analysis (declared `permissions` against known `Capability` values, Phase
7) -> evaluator review (manifest completeness, via Phase 5's
`ChecklistEvaluator`). ACR has no code-execution engine yet — a skill
package is metadata plus human-readable instructions, not executable code
— so sandbox execution / unit / scenario / adversarial tests / benchmark
are honestly reported `SKIPPED`, never faked as passing (master §731: a
candidate must not be promoted merely because it completes one task, and
certainly not on a check that never ran). Skipped stages don't count as
evidence either way; only an explicit `FAILED` blocks `report.passed`.

`acr.skills.evolution` implements master §733-746: "never mutate active
skills invisibly." `create_candidate_version()` writes a new `SKILL.yaml`
under a versioned id (`<base_id>@v<n>`) rather than editing the active
skill's package — both versions coexist as separate `skills` rows, so nothing
is ever silently overwritten. `compare_versions()` reduces master's
quality/tokens/latency/cost dimensions to what ACR can measure without real
usage data yet: `reliability` (Phase 8's utility tracking) and
`token_estimate`; a candidate that regresses on either is not recommended
for promotion. `promote_evolution()` deprecates an active baseline and
activates the candidate; `rollback_evolution()` reverses that — the
baseline is never deleted, so rollback is just reactivating it. Both
respect safe mode (Phase 7).

### A real evolution run (2026-07-29)

`acr skills evolve ui-design-critique` produced `ui-design-critique@v2`, an
instructions.md enriched with concrete numeric thresholds (WCAG contrast,
touch-target sizing, animation timing, spacing rhythm) distilled from
`nextlevelbuilder/ui-ux-pro-max-skill`'s priority table (MIT-licensed,
rewritten for ACR's format rather than copied — see that skill's
`description` field for provenance). `estimate_tokens()` put the richer
instructions at 581 tokens against baseline's measured 416.
`compare_versions()` correctly returned `recommend_promote=False,
"candidate costs more tokens than baseline"` — both versions have `0.0`
reliability (neither has been through a real task yet), so the only
measurable dimension is cost, and the candidate is genuinely more
expensive. `acr improve propose-skill-evolution` accordingly refused to
create a proposal at all ("candidate does not improve on the baseline").

This is the system working as designed, not a failed experiment: master
§738-744's whole point is that a richer skill isn't automatically a better
one, and "more content" is exactly the kind of change that should earn
promotion through evidence (real task outcomes moving `reliability`) rather
than being rubber-stamped for looking more thorough. `ui-design-critique@v2`
stays registered as `experimental` in `<data_dir>/generated_skills/`
(gitignored — evolution candidates are a runtime artifact, not first-party
source, same distinction as `skills/` vs. `data/`) and can be re-compared
once it has real usage data.

## Agents (Phase 10)

`acr.agents.models.AgentSpec` carries the master §749-763 field set (role,
objective, granted skills/tools, token budget, parent/lineage). It is a
plan, not a running process — ACR has no actual subprocess/thread agent
runtime, so "spawning" an agent means executing its objective through the
existing Phase 1 `run_task()` under that plan's constraints, not starting a
new concurrent worker.

`acr.agents.factory.estimate_spawn()` implements master §764-773's
spawn-worth gate *before* any work happens: a deterministic
`SpawnEstimate` (expected quality gain, coordination overhead, security
risk) exposes a `worth_spawning` property, and `spawn_agent()` refuses to
run an objective whose estimate says no unless the caller passes
`force=True` — spawning sub-agents has a real cost (context, tokens,
coordination) that master principle #14 says must be justified, not
assumed. `spawn_agent()` calls the real `run_task()` (Phase 1) with the
spec's provider and objective — no parallel "fake execution" path exists
— then records the real outcome (see "Closing the evidence loop" below).

`acr.agents.planner.plan_agent()` builds an `AgentSpec` using the *real*
Phase 4/6 machinery — `skills.routing.route()` for skill grants and
`tools.exposure.expose_tools()` for tool grants — rather than a new,
parallel selection heuristic. An objective with no matching active skill
or relevant tool legitimately gets an empty `skills`/`tools` list; nothing
is force-populated to make the demo look richer than the registry
actually supports.

`acr.agents.critic.review_agent_task()` reuses Phase 5's
`evaluate_with_panel()` rather than inventing a second evaluation
mechanism for agent output — "review" and "evaluate" are the same
operation applied to a `Task`'s result. A `FAILED` task fails review by
construction; a `COMPLETED` task is scored by the same checklist/exact-match
evaluators every other evaluated task uses.

`acr.agents.topology.AgentTopologyRecord` persists one row per completed
spawn (task class, worker count, model names, skill ids, quality score,
success). `recommend_topology()` implements master §774-793's "let evidence
pick the topology": it refuses to recommend anything until a `task_class`
has at least `min_samples` (default 3) recorded runs meeting
`min_success_rate` (default 0.6) — an opinion formed from one or two runs
would be exactly the unevidenced claim master principle #22 forbids.
Recommendations are per-`task_class`: evidence from `coding` runs never
informs a `research` recommendation.

### Closing the evidence loop (2026-07-29)

`learning.utility.record_skill_outcome()` (Phase 8) and
`agents.topology.record_topology()` (Phase 10) both existed as real,
tested functions — but nothing in application code ever called either
one. `spawn_agent()` ran a real task and returned it; the CLI reviewed it
and printed the result; no code path fed that outcome back into skill
reliability or topology evidence. `routing.route()`'s "check prior
performance" step and `recommend_topology()`'s evidence requirement could
therefore never see real data, no matter how many agents actually ran —
this wasn't "not enough runs yet," it was that runs literally couldn't
move either number.

Fixed at the one choke point every caller shares: `spawn_agent()` now
reviews its own task via `review_agent_task()`, calls
`record_skill_outcome()` for every skill in the spec, and calls
`record_topology()` for the spawn itself. `task_class` became a required
keyword argument (threaded through `agents_plan`/`agents_spawn`'s new
`--task-class` option) rather than inferred — ACR has no classifier model
(`routing.route()`'s own note), so guessing one would silently
misattribute evidence to the wrong class, worse than not recording at
all. `spawn_agent()`'s return type changed from `Task` to
`tuple[Task, PanelResult]` since the review is now computed once, inside
the function that needs it, instead of redundantly by every caller.

Verified with real dogfooding, not just tests: three real `acr agents
spawn --task-class ui-audit` runs against genuinely different objectives.
`acr agents topology ui-audit` went from "insufficient evidence" to a real
recommendation ("3/3 successful runs (100%), mean quality 1.00") purely
from those runs — no seeded/synthetic rows. `dashboard-ui-audit`'s
reliability moved from `0.00`/0 uses to `1.00`/3 uses on the dashboard's
own `/skills` page. Re-running the `ui-design-critique@v2` evolution
comparison from the entry above with this real evidence in place produced
an even more honest result: `reliability: 1.00 -> 0.00, ...
recommend_promote=False: candidate is both less reliable and more
expensive than baseline` — the baseline's reliability is no longer a
default 0.0 two untested versions were tied on, it's now earned.

## Dashboard (Phase 11)

`acr.dashboard` is a presentation layer, not a new subsystem: every view is
a read-only `SELECT` (`acr.dashboard.queries`) or a call into a query
function an earlier phase already wrote (`doctor.run_checks`,
`skills.registry.list_skills`, `security.audit.recent_audit_events`,
`tools.default_tools.build_default_registry`, `routing.models.
build_default_router`). No view invents new scoring, ranking, or decision
logic — the dashboard must not become a second copy of business logic that
already lives somewhere else.

`acr.dashboard.app.create_app()` builds a small FastAPI app with one route
per master §1226-1239 category: `/` (system health, via the same checks
`acr doctor` runs), `/tasks`, `/agents` (topology history), `/memory`,
`/skills`, `/tools` (registered tools + recent `tool.invoke:*` audit
events), `/routing` (the model ladder + live availability, the same data
`acr models list` prints), `/security` (the audit log), `/benchmarks`, and
`/events` (a generic, filterable telemetry feed — this is where token
usage, model-call failures, and skill-validation activity actually live,
since ACR has no separate "cost" or "learning event" table to query
instead). Every template is a plain HTML table — master §1240: "the
dashboard must remain useful without advanced graphics" — so there is no
charting library, no JS framework, and no CDN dependency (the whole page is
one inline `<style>` block, consistent with ACR being local-first and
usable offline).

`acr dashboard serve [--host --port]` runs it via uvicorn. Each request
gets its own `AsyncSession` from a request-scoped FastAPI dependency
(`Depends(get_session)`) built off the same `acr.db.base.make_engine`/
`make_session_factory` every other entry point uses — the dashboard reads
the same SQLite file `acr run`/`acr skills ...`/etc. write to, live, with
no polling or caching layer.

## Visualization (Phase 12)

Master §1242-1256 asks for a "cinematic," "3D cognitive graph" visualization
layer driven by real telemetry. This phase implements the "driven by real
telemetry" requirement in full and deliberately scopes down the rendering
technology — a documented decision, the same way ADR-0001 documents
deviating from the master's literal directory tree, not a silent
reinterpretation:

- **No Three.js / WebGL library.** Vendoring one means downloading and
  committing a third-party binary/minified file — a real action, not a
  free one, and out of scope to do without asking. A CDN `<script>` tag
  avoids the download but adds a hard network dependency to a page that's
  supposed to work fully offline, breaking the local-first requirement
  every other phase has treated as non-negotiable (the mock provider needs
  zero config, Ollama is localhost-only, there's no cloud dependency
  anywhere else in the stack).
- **Hand-written Canvas2D instead.** `acr/dashboard/static/visualization.js`
  is the entire rendering stack: no dependency, no build step, no CDN —
  consistent with every other phase's "ship what you can run with `uv
  run`, nothing else to install."

`GET /api/graph` (`acr.dashboard.app`) is the one new read path: a JSON
projection of `acr.dashboard.queries.memory_type_counts()`,
`recent_tasks()`, `recent_topology()`, and `recent_events()` — the exact
same data the plain-table dashboard already renders, just serialized for
the frontend to poll instead of embedded in server-rendered HTML. No
synthetic/randomized data anywhere: what's on screen is what's actually in
`acr.db`.

`GET /visualization` renders a `<canvas>` and loads the script. The scene:
a center "core" that idle-pulses continuously (master's own described
idle-state effect) and flashes when a new telemetry event arrives since
the last poll; memory-type nodes arranged radially around the core, sized
by record count; recent tasks as status-colored squares; recent agent
spawns as quality/succeeded-encoded diamonds; and a scrolling event-flow
timeline along the bottom. Polling (`fetch` every 2s), not a websocket —
the simplest transport that's still genuinely live, and there's no
existing push/streaming infrastructure this phase would otherwise have to
invent just to serve one page.

### Dashboard and visualization UI/UX overhaul (2026-07-29)

The dashboard was functionally complete but visually default-browser-
styled (unstyled `<table>`s, plain colored text for status, no real type
scale). Rebuilt `base.html` with a real design system reusing the same
tokens the public landing page established (warm palette, copper accent,
sage secondary, monospace-for-labels/sans-for-body pairing) for cross-
surface brand consistency — both light and dark themes, following
`prefers-color-scheme`. Added reusable components (`.metric-card`,
`.pill`, `.table-wrap` for horizontal-scroll safety) and a single
`pill_class` Jinja filter (`acr.dashboard.app._pill_class`) mapping every
status/outcome vocabulary the dashboard displays to one consistent visual
language, replacing the old per-page `status-{{ value }}` string-match
CSS that silently rendered unstyled for any value nobody had added a rule
for. Applied across all 11 content templates; zero changes to
`acr.dashboard.queries` or any route's data logic — presentation only.

The visualization tab specifically got a real research-informed redesign
(competitive review of LangSmith, Langfuse, Helicone, Arize Phoenix, and
W&B's trace/observability UIs, plus Obsidian/Roam/Logseq's knowledge-graph
views — see git history for the full sourced findings). Two load-bearing
conclusions from that research:
- Every observability tool surveyed keeps a table/timeline as the
  *primary* debugging surface and a graph/DAG view as secondary and
  exploratory, never the main way to find out why something failed —
  which validates this dashboard's existing shape (Tasks/Events/Security
  stay tables; Visualization was already the secondary view) rather than
  suggesting a restructure.
- What actually fixes a "pretty but useless" graph (Obsidian's own
  community's description of its graph view past ~200 notes) isn't a
  better layout algorithm — Logseq's fix for Roam's "unusable" graph was
  interactivity (hover, filter, click), not improved physics.

Implemented accordingly, still zero new dependencies (hand-written
Canvas2D, no charting/graph library, consistent with the "no advanced
graphics" scope decision above): real hover tooltips on every shape
(memory ring, task square, agent diamond, event dot) showing the actual
underlying record; a light force-directed layout for memory-type rings
(spring-to-ideal-angle + pairwise repulsion + damping — under 40 lines,
no physics library) replacing the previous fixed circular placement;
drag-to-pin a ring in place (double-click to release); and an HTML legend
above the canvas replacing a paragraph of prose. Colors are read from the
same CSS custom properties `base.html` defines via `getComputedStyle`, so
the canvas automatically matches the active theme instead of carrying a
second, hardcoded color set that would drift out of sync. Verified for
real in the browser (not just read): hover tooltips confirmed showing
actual task/memory content, drag-and-pin confirmed moving and persisting
a ring's position, both light and dark themes and a mobile viewport
checked, `.claude/launch.json` added so `acr dashboard serve` previews
directly in future sessions.

### Neo-cyber alternate theme (2026-07-29)

Added a second, opt-in theme rather than replacing the default one:
`:root[data-theme="cyber"]` in `base.html` redefines every design token
(cyan/magenta-violet duotone on near-black, angular 2px radii and
rectangular pill tags instead of 4px/999px rounded, a scanline overlay and
a faint accent-colored grid texture, neon glow via a shared
`--glow-accent`/`--glow-danger` box/text-shadow token) — a deliberate
single dark world, not a light/dark pair, since a "neo cyber" identity
doesn't have a coherent light-mode counterpart; the existing warm
light/dark theme is untouched and stays the default.

A nav toggle (`#theme-default` / `#theme-cyber`) sets `data-theme` on
`<html>` and persists the choice to `localStorage["acr-theme"]`; an inline
`<head>` script (not deferred) applies the saved choice before first paint
so navigating between pages never flashes the wrong theme. Because
`visualization.js` already reads its palette from CSS custom properties at
render time (see above), the canvas graph re-themes automatically with no
JS changes to its color logic — the only addition there is a `--canvas-glow`
token (a plain number, 0 outside the cyber theme) that `withGlow()` reads
to apply real `ctx.shadowBlur`/`shadowColor` to the core, memory rings,
task/agent markers, and event dots, always resetting `shadowBlur` after
each shape since canvas shadow state otherwise leaks into whatever draws
next.

One real bug surfaced and fixed while building this: `body` originally
declared `background: var(--bg);` (shorthand) followed by a separate
`background-image: var(--bg-texture);` (longhand). Mixing a `var()`
shorthand with an explicit longhand override of a sibling sub-property is
a known CSS footgun — inspecting the parsed CSSOM directly
(`document.styleSheets`) showed the browser's expanded `background-color`
sub-value coming back empty, and the page fell back to a stale color
instead of the current theme's. Fixed by using `background-color: var(--bg)`
as its own explicit longhand instead of the shorthand. Verified via the
browser: `getComputedStyle` on `--bg` (correct immediately in both cases)
vs. on the actual `background-color` (broken before the fix, correct
after), all cyber-theme text/background contrast pairs computed live and
passing WCAG AA (worst case 4.85:1), theme persistence across a page
navigation, and both toggle directions. (A `transition: background-color
0.2s` on `body` made `getComputedStyle` reads taken immediately after a
programmatic click look stale in this session's headless preview — that
environment doesn't composite frames, so CSS transitions there never
settle; confirmed the real cascade was correct throughout by forcing
`transition: none` and re-reading, unrelated to the shorthand bug above
and not an issue for an actually-rendering browser.)

### Table sort and filter (2026-07-29)

`static/tables.js` (vanilla JS, no dependency, consistent with
`visualization.js`'s own "no charting library" scope decision) makes every
table already rendered inside a `.table-wrap` sortable by clicking any
`<th>` (numeric-aware via the existing `.num` class tables already use for
right-aligned columns) and, for tables with 2+ data rows, adds a
client-side text filter above it. One `<script>` tag in `base.html` — no
per-template changes across the 9 pages with real tables, matching the
`pill_class` filter's "one shared mapping, not eleven copies" precedent.
Everything sorted/filtered is already fully rendered server-side; this
only reorders/hides existing DOM rows, no additional request. Degrades
safely if JS fails to load: `.sortable`/`data-sort` styling only applies
once `tables.js` actually adds the class, so an unstyled, unsorted,
unfiltered — but still fully readable — table is the fallback, not a
broken one.

Verified live in the browser, not just via the regression test asserting
the script tag and asset are served: clicked a real `<th>` on `/security`
and confirmed the underlying rows actually reordered (ascending, then
descending, comparing DOM order before/after via `getComputedStyle`-
adjacent row inspection rather than trusting the click alone); typed into
the filter input on the same page and confirmed the correct row count
stayed visible vs. hidden; confirmed zero filter boxes render on the
`/proposals` empty-state page (0 data rows) where one would just be noise.

## Integrations: MCP server (Phase 13, first sub-slice)

Master §1707-1713 lists six integration targets (MCP, Claude Code, Codex,
GitHub, browser automation, desktop app) under one phase. They're
heterogeneous enough — some need no credentials at all, others need a
GitHub token or a whole new packaging toolchain (Tauri, for "desktop app")
— that attempting them together would violate the master's own "smallest
complete vertical slice" rule (§65-66). MCP server exposure went first: no
credentials, and it's the highest-leverage piece — any MCP client (Claude
Code, Claude Desktop, anything else speaking the protocol) can use ACR's
memory, skills, and task execution the moment this runs.

`acr.integrations.mcp_server.create_mcp_server()` doesn't add a new
integration surface's worth of business logic — it exposes what already
exists through a new *transport*. `memory_search`, `skill_search`, and
`web_fetch` are the identical `ToolSpec` handlers Phase 6/13's
`acr.tools.default_tools` registered, invoked through the same
`acr.tools.invocation.invoke_tool()` permission+audit seam Phase 7 built
(an external MCP client is a *more* untrusted caller than the local CLI,
not a less — it goes through that check rather than around it). The
server's fixed grant set is exactly `{memory.read, skill.read,
network.read}` — nothing beyond what those three read-only tools declare
(master §1131-1149: default deny). `run_task` mirrors what `acr run`
already does: the zero-config mock provider, no cost, no external calls —
real provider routing for MCP-triggered tasks is future work, the same
caveat the CLI's own `run` carries today.

`acr mcp serve` defaults to stdio (how Claude Code/Desktop launch a local
MCP server as a subprocess); `--transport sse` or `--transport
streamable-http` with `--host`/`--port` serve it over HTTP instead. Both
transports were manually smoke-tested end to end.

### Web fetch tool

`acr.tools.web_fetch` is master §1707-1713's "browser automation," scoped
to a plain HTTP(S) GET plus stdlib `html.parser`-based text extraction —
not a real browser. The user chose this explicitly over Playwright:
real interactive browser automation needs to download a ~100-300MB
Chromium binary on first use, which is a real action requiring sign-off,
not something to trigger silently mid-build; `httpx` (already a
dependency) needs nothing new to install. Fetched content is untrusted
(master §1122-1130 — `RETRIEVED_CONTENT` trust tier, same as retrieved
memory) and is run through `acr.security.injection.scan_for_injection()`
before being returned — flagged via a `suspicious`/`matched_patterns`
field, never silently blocked, same contract every other
`scan_for_injection()` call site follows. Registered as a normal
`ToolSpec` (`permissions=["network.read"]`,
`side_effect_level=READ_ONLY`), so it goes through the exact same
permission+audit path as every other tool — `acr tools fetch <url>` on the
CLI, or `web_fetch` over MCP.

Fixing this tool's tests surfaced a real, pre-existing bug in
`acr.tools.exposure`: `_score()` tokenized on *every* word including
stopwords, so a bare function word like "a" appearing in both a task
description and an unrelated tool's description counted as "relevant"
overlap (`"compile a container image"` matched `web_fetch` purely on the
word "a"). Fixed by promoting `acr.core.fts_query`'s stopword-filtered
tokenizer to a shared `tokenize()` function, used by both FTS search and
tool exposure — the same "does this text meaningfully overlap with that
text" question should mean the same thing everywhere in ACR. Filtering
stopwords out of the query mechanically raises every remaining match's
relative score, which pushed `_MIN_RELEVANCE` from `0.25` to `1/3` to
keep a single shared *content* word (e.g. two tools both named
`*_search`) from crossing the threshold on its own — the exact scenario
the module's own docstring already described as the thing to prevent.

### Real browser automation (Playwright)

`acr.tools.browser` is the JS-rendering complement to `web_fetch`: a real
headless Chromium instance via Playwright, for pages `web_fetch`'s plain
GET can't see anything meaningful from. Adding this was an explicit,
separate user decision from `web_fetch`'s original scope-down — the
`playwright` Python package is a normal dependency (added via `uv add`,
~36MB, no different from any other package this project has added), but
the actual browser binary (`playwright install chromium`, historically
~100-300MB on Windows) is a distinct action this project never triggers
silently. In this case the binary was already present on the build
machine from prior unrelated use, so no download actually happened here —
but the tool's own error handling (`BrowserNotInstalledError`, raised when
Playwright reports its "Executable doesn't exist" error) still exists for
any environment where it isn't, pointing at the exact command to run.

Same trust posture as `web_fetch` and `github_search`: rendered page text
is untrusted content and is run through `scan_for_injection()` before
being returned. Registered the same way as every other tool
(`permissions=["network.read"]`, `READ_ONLY`) — `acr tools browse <url>`
on the CLI, or `browser_fetch` over MCP. Manually smoke-tested against a
real public page (`https://example.com`) in addition to the automated
test suite's local-server tests.

### GitHub search tool

`acr.tools.github_search` is master §1707-1713's "GitHub" integration,
scoped to read-only search (per explicit user decision — write actions
like creating issues/comments are a distinct "publish/post" decision that
needs per-action confirmation, not a blanket grant). It shells out to the
`gh` CLI, already authenticated on this machine — no token is ever read,
stored, or passed through ACR's own code; `gh` owns its own credential
storage entirely, so nothing GitHub-shaped touches ACR's memory, logs, or
telemetry. `gh api "search/issues?q=..."` covers both issues and PRs in
one call. Registered the same way as every other tool
(`permissions=["network.read"]`, `READ_ONLY`) — `acr tools github-search
"<query>"` on the CLI, or `github_search` over MCP. Issue/PR titles are
untrusted external content (real-world testing turned up a spam issue
titled to look like a rate-limit error message), so each result is run
through `scan_for_injection()` the same way `web_fetch` scans fetched
pages.

`_run_gh_api()` has its own timeout (`GhCliTimeoutError`, 15s) and a clear
`GhCliNotFoundError` if `gh` isn't on `PATH` — a real gap an early manual
smoke test found: an unencoded query string with a space in it caused `gh
api` to hang rather than fail cleanly, so the query is now
percent-encoded (`urllib.parse.quote`) before being embedded in the
endpoint, and any future hang is bounded rather than blocking the caller
forever.

## Public launch baseline (Phase 14)

Master §1714-1720 lists website, docs, GitHub, security page, downloads,
and support link. The repo (`hbkdad/arc`) is already public on GitHub, so
this phase is baseline OSS hygiene for a repo that's already visible, not
a real product launch — explicit user decision, not a marketing push. No
separate marketing site was built; the README is the de facto public
entry point for now (§1714's "website" bullet, deliberately scoped down
the same way Phase 12 scoped down "3D" — documented, not silently
reinterpreted).

- `LICENSE` — MIT, per explicit user choice.
- `SECURITY.md` — points to GitHub's private vulnerability reporting
  (Settings → Security → "Report a vulnerability"), which was OFF for
  this repo and is now explicitly enabled (`gh api --method PUT
  repos/hbkdad/arc/private-vulnerability-reporting`, per explicit user
  confirmation before flipping a real repo setting).
- `CONTRIBUTING.md` — dev setup, the quality gate, and a pointer to
  `ACR_MASTER_SYSTEM_PROMPT.md`/this file as the actual source of truth
  for how the project is built, since that's genuinely how it works here.
- `README.md` — refreshed: the stale hardcoded "Status: Phase 0" line is
  gone (it could only ever drift out of sync with this file); replaced
  with a real "what's here" summary and links to `LICENSE`/`SECURITY.md`/
  GitHub Issues. `pyproject.toml` gained `license = "MIT"` and `readme =
  "README.md"`.
- "Downloads" (§1714) isn't addressed yet — no PyPI package exists, and
  publishing one is a distinct action needing its own credentials/account,
  not assumed here.

## Controlled self-improvement (Phase 15, final master-spec phase)

Master §1721-1727 lists experiments, strategy optimization, skill
evolution, routing optimization, and autonomous proposals under one
phase. "Skill evolution" already existed (Phase 9); this phase's real
contribution is the "controlled...autonomous proposals" part — the
gate every self-improvement action goes through — applied to that one
existing mechanism. Explicit user framing for this phase: guardrails, yes,
but the system should genuinely be able to improve itself "for the design
and intent it was given" — not artificially hobbled beyond what's needed
for safety.

`acr.learning.proposals.Proposal` is the gate itself: evidence (right now,
Phase 9's `EvolutionComparison`) plus a recommendation, persisted, never
an applied change by itself. `propose_skill_evolution()` only ever creates
a proposal when `compare_versions()` actually recommends promotion —
there's no "propose a regression and let the human veto it" path; a
non-improvement isn't a rejected proposal, it's simply not evidence of
anything to propose (`propose_skill_evolution()` returns `None`, not a
`Proposal`, in that case — same "never publish a result the evidence
doesn't support" reasoning as every prior phase's evaluation code).

Two settings implement the guardrails, both explicit user decisions:
- `Settings.self_improvement_enabled` (`ACR_SELF_IMPROVEMENT_ENABLED`,
  **on** by default) — the master kill switch. `propose_skill_evolution()`
  refuses outright when this is off.
- `Settings.auto_apply_proposals` (`ACR_AUTO_APPLY_PROPOSALS`, **off** by
  default) — proposals require explicit human approval
  (`acr improve approve <id>`) before taking effect unless this is turned
  on, in which case a recommended proposal applies itself immediately
  (status `auto_applied` rather than `pending`). Off-by-default was the
  explicit choice: approval-gated is the safe default, autonomous
  application is the opt-in escape hatch, never the other way around.

Scope boundary, also explicit user intent ("for the design and intent it
was given," not unboundedly): a proposal can only ever invoke a mechanism
this codebase already exposes as a reviewable, gated operation
(`acr.skills.evolution.promote_evolution`, itself safe-mode-aware via
`set_status()`). There is no proposal kind — and none is planned — that
edits ACR's own source code, dependencies, or permission grants; those
stay entirely outside what "self-improvement" means in this system. Every
proposal decision (create/approve/reject/auto-apply) is audit-logged the
same way every other mutating operation in ACR is (Phase 7's
`record_audit_event()`).

`acr improve propose-skill-evolution/list/approve/reject` on the CLI; a
read-only `/proposals` dashboard view (Phase 11's pattern — reuses
`list_proposals()` directly, no duplicated query logic) shows current
settings and proposal history, with approve/reject staying CLI-only
(the dashboard has no form/write path anywhere, by design).

**Deliberately not built** in this slice — real gaps, not oversights: a
second proposal kind for anything beyond skill evolution (routing
threshold tuning, "strategy optimization," an "experiments" runner)
would need its own evidence source before it could honestly propose
anything, and none of those evidence sources exist yet. Building the
proposal *mechanism* generically (this phase) before inventing more
evidence sources to plug into it (future phases, only once something
concrete needs them) is the same "smallest complete vertical slice,
no speculative infrastructure" discipline every phase in this repo has
followed.

## Commands available today

```bash
uv run acr doctor              # Python version, data dir, DB, mock + Ollama providers
uv run acr version
uv run acr run "objective" [--min-quality-tier N]  # 0=mock (default); raise for Ollama/cloud
uv run acr context compile "objective" --budget 2000  # compile + print a ContextBundle
uv run acr skills register <path>        # parse SKILL.yaml, add/update the registry
uv run acr skills list [--status active]
uv run acr skills search "query"
uv run acr skills activate <id> --status active   # manual lifecycle transition
uv run acr skills route "task description" [--task-class X]
uv run acr benchmark run memory-recall     # execute a suite for real, persist the run
uv run acr benchmark history memory-recall # compare the two most recent runs
uv run acr waste duplicates                # duplicate memory content across subjects
uv run acr waste utilization               # compiled vs. referenced context tokens
uv run acr models list                     # routing ladder + live availability
uv run acr models route "prompt" [--min-quality-tier N]
uv run acr tools list
uv run acr tools expose "task description" [--max-tools N]
uv run acr tools invoke <name> --query "..." [--limit N]   # permission + safe-mode checked
uv run acr tools fetch <url> [--max-chars N]                # http(s) GET + text extraction
uv run acr tools github-search "<query>" [--limit N]         # read-only, via the gh CLI
uv run acr tools browse <url> [--max-chars N]                # real headless-browser render
uv run acr safe-mode                       # show whether ACR_SAFE_MODE is on
uv run acr security scan "text"            # prompt-injection heuristic scanner
uv run acr security audit [--limit N]      # recent audit events
uv run acr learn distill <task-id>         # trace -> compact memory candidate
uv run acr learn promote [--min-utility N --min-successful-uses N]
uv run acr learn generate-skills [--min-repeats N]
uv run acr skills validate <id> [--check-tools]
uv run acr skills evolve <id> [--description "..."]
uv run acr skills compare-evolution <baseline-id> <candidate-id>
uv run acr skills promote-evolution <baseline-id> <candidate-id>
uv run acr skills rollback-evolution <active-id> <restore-id>
uv run acr agents plan "objective" [--role X --token-budget N --task-class X]  # AgentSpec via real routing + exposure
uv run acr agents spawn "objective" --task-class X [--force]  # required: closes the evidence loop -- see below
uv run acr agents topology <task-class>                     # evidence-gated worker-count recommendation
uv run acr explain <task-id>                 # replay a task's real telemetry trail, no narrative
uv run acr learn failures "objective" [--task-class X --limit N]  # similar past FAILURE memories
uv run acr learn self-practice [--limit N --min-quality-tier N]   # run each active skill's own applicability
uv run acr memory gc-plan [--superseded/quarantined/stale-candidate-*-days N]  # dry run
uv run acr memory gc-apply [same flags]      # re-plans and archives every eligible record
uv run acr memory calibration [--min-uses N] # does stored confidence predict outcomes?
uv run acr backup create [--output PATH]     # zip + SHA-256 manifest of the data dir
uv run acr backup restore <archive> --target-dir PATH [--force]
uv run acr models usage                      # real per-provider calls/tokens/estimated cost
uv run acr dashboard serve [--host --port]   # dashboard + /visualization: http://127.0.0.1:8765
uv run acr mcp serve [--transport stdio|sse|streamable-http] [--host --port]
uv run acr improve propose-skill-evolution <baseline-id> <candidate-id>
uv run acr improve propose-routing-optimization <task-class> <current-model> <candidate-model>
uv run acr improve list [--status pending|approved|rejected|auto_applied]
uv run acr improve approve <proposal-id>
uv run acr improve reject <proposal-id>
uv run alembic upgrade head    # dev path (reads alembic.ini)
uv run acr db upgrade          # same result, also works from a pip/uv-tool install
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

`agents spawn --task-class` is required (not optional) as of 2026-07-29:
it's how a spawn's outcome feeds back into skill reliability and topology
evidence (`record_skill_outcome()`/`record_topology()` — see "Closing the
evidence loop" above); ACR has no classifier to infer one safely.

Memory *writing* for arbitrary facts is still library-level only
(`acr.memory.write_controller`) — `remember_failure()`/`remember_decision()`
exist as typed helpers (see `acr.memory.schemas`), but there's no
`acr memory remember ...` CLI verb for them yet.

## Real provider routing (post-Phase-15 hardening)

Every phase built the routing ladder (Phase 6) and the two primary task-
execution entry points (`acr run`, MCP's `run_task`), but the entry points
never actually used the ladder — both hardcoded `MockProvider()` directly,
so a user with Ollama running or a cloud API key configured had no way to
actually reach it short of `acr models route`. Fixed by routing both
through `ModelRouter.select(min_quality_tier=...)` instead:
`--min-quality-tier` (CLI) / `min_quality_tier` (MCP tool arg) default to
`0`, which is always the free, always-available mock provider — identical
behavior to before this existed, so nothing that depended on the old
hardcoded-mock behavior breaks. Raising the tier opts into whatever's
actually configured (Ollama first, then cloud, per the ladder's cost
ordering).

### Per-provider usage and cost tracking (2026-07-29)

The `/routing` dashboard page showed the ladder's *configuration*
(quality tier, price, live availability) but never any *usage* — a user
who'd actually spent real Claude/Anthropic tokens through ACR had no way
to see it there. `acr.telemetry.usage.usage_by_provider()` closes that
purely by aggregating `model.call.completed` `TelemetryEvent` rows
`core.execution.run_task()` already writes — no new instrumentation
beyond adding `input_tokens` alongside the pre-existing `output_tokens` in
that one event payload. Cost is estimated against each provider's
*current* `cost_per_1k_tokens`; there's no historical price catalog, so
older calls aren't re-priced retroactively — stated plainly in both the
CLI (`acr models usage`) and the dashboard, not hidden. A provider with
real usage but no currently-configured `ModelProfile` still shows its
call counts, just with cost fields `None` rather than being dropped —
real usage is never hidden for lack of a current price.

`/routing` gained a second section (metric-grid of call counts + a full
usage table) built from the same aggregation, `app.py`'s `/routing` route
now takes a `session` dependency it didn't need before. Verified live,
not just via tests: ran a real `acr run` against Ollama (this machine's
own `ACR_DEFAULT_MIN_QUALITY_TIER` opt-in routes there), confirmed the
row landed in `data/acr.db` via a raw sqlite3 query, then hit a real
"dashboard shows nothing" symptom that turned out to be the preview
server's own Python process not having been restarted — template/static
edits hot-reload in this dev setup, but a `app.py` route-function change
doesn't, since that's compiled into the already-running process. Restarted
the preview server and the real numbers (5 mock calls, 2 Ollama calls,
real token counts) appeared correctly. No Claude/Anthropic usage shows
yet simply because none has gone through ACR's own routing in this
environment — the tracking is real and will show it the moment that
changes; this session's own MCP conversation with Claude Code is a
separate system from ACR's routing ladder, not a source this table draws
from.

Wiring this up for real (rather than leaving it as an untested code path)
immediately surfaced a real, previously-invisible bug:
`acr.providers.ollama.OllamaProvider` hardcoded `DEFAULT_MODEL =
"llama3.2"` — a model name that has no special status in Ollama (it ships
with none pulled by default) and simply wasn't present on the machine
this was tested on, so every real completion attempt 404'd. Fixed by
making model selection lazy and auto-detecting: `model=None` (the new
default) resolves to the first result of `list_models()` at completion
time rather than a hardcoded guess, with a clear `OllamaNoModelError`
pointing at `ollama pull` if literally nothing is pulled.
`Settings.ollama_model` (`ACR_OLLAMA_MODEL`) lets a user pin a specific
model instead. Verified end-to-end against this machine's real, already-
running Ollama daemon (`qwen2.5-coder:1.5b`, `llama3.1:8b` actually
pulled) — `acr run "..." --min-quality-tier 1` now genuinely completes via
a local model, not just in theory.

`Settings.default_min_quality_tier` (`ACR_DEFAULT_MIN_QUALITY_TIER`) is a
persistent opt-in on top of the above: set it once and every `acr run`/MCP
`run_task` call that doesn't explicitly pass `--min-quality-tier`/
`min_quality_tier` uses it from then on, instead of needing the flag on
every invocation. The zero-config out-of-box default (tier `0`, mock-only)
is unchanged — this only affects a caller who's deliberately configured a
preference.

### Dashboard visual overhaul: charts + a real task timeline (2026-07-29)

The node graph on `/visualization` was, by explicit user feedback, the
only real *metric* surface on the dashboard, and it's built entirely out
of circles — fine for showing relationships (that's what it was designed
for), a poor fit for "how much," "how many," or "in what order." Research
before touching anything: a competitive read of LLM-observability tooling
(Portkey, MLflow, Langfuse) and Grafana's own panel taxonomy. The
consistent finding — Langfuse's own answer to "beyond circles" is a real
Gantt timeline for execution sequence plus line/bar charts for cost and
latency, with a node/relationship graph kept as a secondary, opt-in view,
never the primary metric surface. That's the shape this pass followed,
not a redesign of the graph itself (its physics + hover/pin interactivity
was already a considered, researched choice — see "Phase 12" above — and
stays as-is).

Still bound by the same constraint that shaped the graph in the first
place: "the dashboard must remain useful without advanced graphics"
(master §1240) — no charting library, no CDN script, no build step.
Every new chart is hand-rolled, in a new `static/charts.js` shared across
pages:

- **`ACRCharts.barChart`** — horizontal bars (memory type counts, routing
  usage/cost by provider).
- **`ACRCharts.pairedBarChart`** — two bars per group with a shared
  legend (confidence calibration: predicted vs. actual per bin).
- **`ACRCharts.sparkline`** — a small inline SVG trend line with an area
  fill (overview page: tasks/hour and events/hour over the last 24h).

None of these are circles/donuts — a deliberate choice given the user's
specific complaint, not just a style preference. Every color is a CSS
custom property (`var(--accent)`, `var(--ok)`, ...) referenced through
`chart-*` classes in `base.html`, not a hex value computed in JS, so an
already-rendered chart re-themes for free on the theme toggle — no
re-render needed, unlike the live canvas graph which recomputes theme()
every frame anyway.

New real data sources, no synthetic/random values anywhere:

- `acr.dashboard.queries.tasks_created_per_hour()` /
  `events_per_hour()` — real hourly counts via SQLite `strftime`
  grouping, zero-filled for every hour boundary in the window (an hour
  with no activity plots as a real zero, not a gap that would silently
  compress the time axis).
- `/memory` now calls `acr.evaluation.calibration.compute_calibration()`
  (built in the "next-level" batch above, but never wired into the
  dashboard until now — only reachable via `acr memory calibration`
  before this) and renders its reliability curve as a real paired-bar
  chart, with the real "not enough recorded outcomes yet" empty state
  when no memory has any recorded successful/failed use, not a
  fabricated curve.
- `/api/graph`'s `tasks` now include `created_at` (previously only
  `updated_at`) — needed for the timeline's start-to-end bars, and a
  genuine gap in the original Phase 12 payload once a real Gantt view
  needed both ends of a task's lifetime.

**The timeline view**: `/visualization` gained a Graph/Timeline toggle
(same `.theme-toggle` pattern as the existing default/neo-cyber switch,
persisted to `localStorage`). Timeline is a second `<canvas>`, drawn by
new functions in the existing `visualization.js` (not a separate file —
it already owns theme reading, DPR scaling, and the poll loop against
`/api/graph`, all directly reusable): each recent task becomes a
horizontal bar from `created_at` to `updated_at` (or "now" if still in
flight), colored by status, with real hover tooltips. `drawTooltip()` was
generalized to take an explicit `ctx`/item rather than reading module-level
`hovered`/`dragging` globals, since the timeline needed its own parallel
hover-target/hit-test state (rect containment, not circle-radius) without
disturbing the graph's existing drag-to-pin interaction.

Two real bugs caught before shipping, both against real rendered output
rather than assumed correct:

- **Script-order bug**: `charts.js` was first added at the bottom of
  `base.html` (same position as `tables.js`), but unlike `tables.js`
  (which only reacts to already-rendered tables and is order-independent),
  every chart-rendering page has an inline `<script>` *inside*
  `{% block content %}` that calls `ACRCharts.*` synchronously at parse
  time — which runs before a script tag placed after `<main>` has even
  been requested. Every chart rendered as a silent blank `<div>`, no
  console error, no exception — `ACRCharts` was simply `undefined` at
  the point of the call inside a plain (non-deferred) `<script>` tag.
  Caught by opening the running dashboard in-browser and checking
  `document.getElementById(...).innerHTML.length` directly rather than
  trusting that "no console error" meant "it worked." Fixed by moving
  `charts.js`'s `<script src>` tag to immediately before `<main>`, and
  locked in with `test_charts_js_loads_before_page_content_that_calls_it`.
- **`requestAnimationFrame` never fires against a non-composited
  Browser-pane tab**: `document.hidden` is `true` in this tool's preview
  environment, and per spec browsers don't run rAF callbacks for a hidden
  document — so the *existing* graph canvas and the *new* timeline canvas
  both read back as fully transparent (zero non-alpha pixels) when
  inspected via `getImageData()`, even though nothing was actually wrong.
  Not a regression — re-implementing the exact same coordinate math in a
  one-off script against the real fetched `/api/graph` data (bypassing
  the rAF wrapper entirely, painting directly) confirmed real, finite,
  correctly-positioned bars. Documented here rather than silently
  reported as "verified" with a screenshot that doesn't exist for this
  session — visual/pixel confirmation of anything `requestAnimationFrame`-
  driven isn't currently possible through this tool's preview surface;
  server-rendered content (everything except the two `<canvas>` views)
  was verified normally.

### Code-review hardening pass (2026-07-29)

A systematic review pass (three independent reviewers, one per subsystem
area) found and fixed several real, previously-untested issues — not
found by manually stepping through a milestone, but by dedicated review:

- **SSRF**: `web_fetch`/`browser_fetch` validated the URL scheme but never
  the host, and both take a caller-supplied URL an MCP client (a more
  untrusted caller than the local CLI) controls directly. Now blocks
  link-local/multicast/reserved addresses (the cloud-metadata SSRF class)
  unconditionally, re-validated on every redirect hop — deliberately does
  *not* block ordinary loopback/private ranges, since reaching a user's
  own local services (Ollama, a dev server under test) is legitimate,
  expected local-first usage.
- **Relevance ranking**: SQLite FTS5's `bm25()` is `<=0` and grows *more
  negative* (not more positive) with match strength/corpus size; both
  `memory.retrieval` and `skills.routing` assumed the opposite
  (`1/(1+rank)`), which silently went negative once a table held a few
  hundred rows — in `skills.routing` this clipped `applicability` to 0 and
  dropped a genuinely relevant skill from routing candidacy entirely, a
  bug that got worse the longer ACR ran. Fixed with a shared, sign-correct
  `core.fts_query.bm25_to_relevance()`.
- **Model escalation ladder**: `complete_with_escalation()` only guarded
  `is_available()`, not the actual `complete()` call — a mid-ladder
  failure (Ollama with no model pulled, a cloud provider timing out) blew
  up the whole call instead of falling through to the next candidate,
  defeating the ladder's purpose. Now tolerates a per-candidate failure
  and keeps trying.
- **Memory trust**: a low-confidence correction (`SUPERSEDE_EXISTING`)
  always became `CONFIRMED` status with no confidence check, unlike a
  brand-new fact (which needs `confidence >= 0.75`) — a weakly-evidenced
  correction could become the trusted, temporally-current value for its
  subject without earning that trust level.
- **spawn_agent's cost/risk gate**: documented as something `spawn_agent()`
  itself enforces, but the check only lived in the CLI's `agents spawn`
  command; `spawn_agent()` ran unconditionally. Moved the enforcement into
  the function itself (`SpawnNotWorthwhileError`, `force=True` to
  override) so a future caller can't silently bypass it.
- Smaller consistency fixes: `openai_compatible.py` hard-indexed its
  response body where `anthropic_compatible.py` already parsed
  defensively; `acr improve list --status`/dashboard `/proposals?status=`
  crashed on an invalid value instead of a clean validation error;
  dashboard `/tools` built its invocation list from an event-type-agnostic
  query filtered *after* limiting, letting non-audit telemetry crowd out
  real tool invocations; `security.secrets.redact_mapping()` didn't
  recurse into a list nested inside a list.

Also closed real test-coverage gaps found alongside this (90% → 95%
overall): `anthropic_compatible.py`/`openai_compatible.py` had zero
coverage on their actual request/response handling (only the no-API-key
short-circuit was tested), and `doctor.py`/`github_search.py`/
`browser.py` had untested error-handling branches — the same shape of gap
that hid the Ollama hardcoded-model bug above.

### Ollama reliability fixes (real-hardware measurements, 2026-07-29)

Investigating "why doesn't ACR actually use my running Ollama daemon by
default" (see "What's left" below for why the *default* itself isn't
changing) surfaced two more real, measured bugs in
`acr.providers.ollama`, on top of the earlier hardcoded-model fix:

- **`is_available()`'s 1.0s timeout was too tight.** A real Ollama daemon
  was demonstrably running and reachable (`curl` returned instantly), but
  `OllamaProvider().is_available()` reported it unreachable. Root cause:
  a *fresh process's first* httpx request carries real cold-start
  overhead — measured 1.2-7.2s across repeated runs on this Windows
  machine — before any bytes cross the wire (a warmed-up client in the
  same process, or `curl`, both stayed fast). Every `acr` CLI invocation
  is a fresh process, so this hit every single availability check, not
  just a first one. Raised to 5.0s.
- **`complete()`'s 60s timeout was too tight for CPU-only inference.**
  Measured directly against a real, already-warm (2.2s load time) local
  model: ~10 seconds per generated token with no GPU acceleration. At the
  default `max_output_tokens=512`, 60s wasn't enough to produce even 6
  tokens — meaning close to *every* real completion would fail via
  timeout on exactly the "run it on your own modest hardware" profile
  this local-first tool is built around. Raised to 300s.

Both were verified end-to-end for real after the fix (not just unit
tests against a fake server): `acr run "..." --min-quality-tier 1`
genuinely completed via the real local daemon, ~82s wall clock, which
would have failed at the old 60s ceiling. A regression-guard test asserts
both constants stay generous so a future "simplification" can't quietly
reintroduce either regression without re-measuring against real hardware
first.

`acr doctor` also now surfaces the actual one-command fix when it
matters: if Ollama is reachable but `default_min_quality_tier` is still
0, `provider_ollama`'s detail names `ACR_DEFAULT_MIN_QUALITY_TIER`
directly instead of a bare "not reachable"/"OK" that leaves a user
guessing why `acr run` still used mock. This is deliberately *not* a
change to the routing default itself — `min_quality_tier=0` must stay
deterministically mock so scripts/automation depending on that exact,
already-tested guarantee never break — just a fix to make the existing
opt-in path visible.

### Post-launch audit (2026-07-29)

A second, broader review pass after the public launch, six independent
lenses instead of subsystem slices this time (dependency/supply-chain,
performance/scalability, test quality, documentation accuracy,
adversarial security red-team, and real-world user research), specifically
choosing lenses the first hardening pass hadn't already covered rather
than re-treading the same ground:

- **Most severe finding: the MCP `run_task` tool bypassed permission and
  audit entirely.** Every other MCP tool goes through `invoke_tool()`'s
  seam; `run_task` called the router and task engine directly. Since
  `min_quality_tier` is a caller-supplied MCP argument, any client could
  force a real, billed cloud completion with zero capability check, zero
  audit trail, on an arbitrary objective. Fixed by gating the *resolved*
  provider's actual cost behind `Capability.CREDENTIAL_USE` (not in the
  MCP server's fixed grant set, so cloud tiers are denied+audited) and
  audit-logging every call, granted or denied — closing both the
  cost/DoS vector and the audit gap in one fix.
- **Real concurrency bug**: SQLite's default rollback-journal mode holds
  an exclusive write lock for a task's full duration; the dashboard polls
  `/api/graph` every 2s. Leaving the dashboard open during a real
  (non-mock) completion hit `database is locked`. Fixed with WAL mode +
  a more generous busy_timeout.
- **Missing indexes** on the exact columns the dashboard's live-polling
  queries sort by (`ORDER BY created_at/updated_at`) — the earlier
  hot-path-indexes migration covered filter/group columns but missed
  these. New migration adds them.
- **Unbounded response buffering** in `web_fetch`/`browser_fetch`:
  neither capped how much a fetched page could grow before `max_chars`
  truncation applied. `web_fetch` now streams with a byte cap;
  `browser_fetch` truncates in-page (JS) before the text crosses the CDP
  protocol, rather than after.
- **Dependency/supply-chain audit came back clean** — every pinned
  version (jinja2, starlette, h11, pydantic, playwright, mcp, and others)
  already carries the fix for every CVE found against it; no unused
  dependencies, no GPL-family licenses.
- **Test suite audit came back strong** — out of ~340 tests, only one
  real weak-assertion finding (a topology test accepting a 2-value range
  where the math is deterministic), now pinned to the exact value.
- **Real user research** (not guessing): pulled real GitHub issues/
  discussions from Ollama, mem0, and MCP-ecosystem threads. Recurring
  patterns most relevant to ACR: persistent-memory systems accumulate a
  lot of low-value/duplicate entries without a quality gate (mem0's own
  issue tracker documents this in detail); "local-first" claims lose
  trust fast if any path secretly needs a cloud account; MCP servers
  broadly have a low trust bar industry-wide, so visible
  reliability/documentation matters more than existence. Not acted on
  yet — flagged here as real, sourced input for whatever comes after the
  launch response is in, not applied blind.

## Continuous integration

`.github/workflows/ci.yml` runs on every push to `main` and every PR:
`ruff check`, `ruff format --check`, `pyright`, a from-scratch `alembic
upgrade head` (catches migration-ordering bugs the in-memory
`Base.metadata.create_all()` test fixture can't — every real migration
this project has wants that guarantee too, not just this one), then the
full `pytest` suite. Deliberately does **not** run `playwright install
chromium`: that's a large, separate download this project has treated as
requiring explicit sign-off everywhere else (Phase 13), and making it a
CI-run side effect on every push would quietly violate that same
principle. `tests/test_tools_browser.py` already skips those cases
gracefully when the binary is absent, so CI is honest about what it
covers rather than silently green over untested code. Single-OS
(`ubuntu-latest`) for now — no evidence yet of a Windows/macOS-specific
bug that would justify a matrix (master principle: no infrastructure
ahead of need). Confirmed passing for real on GitHub's own runners (not
just locally simulated) before this was written up.

## Claude Code integration

`.mcp.json` at the repo root is a project-scoped MCP server registration
for Claude Code specifically — `acr mcp serve` over stdio, no arguments,
matching the format Claude Code's own current documentation specifies
(`mcpServers.<name>.{type,command,args}`; verified rather than guessed).
Deliberately has **no** hardcoded absolute path in `args` — a public
repo's `.mcp.json` travels with every clone, and Claude Code spawns the
server with its working directory set to wherever the project actually
is, so hardcoding this machine's path would silently break for anyone
else. Claude Code prompts for approval the first time a project with a
`.mcp.json` opens (`⏸ Pending approval` until then), so committing this
file can't make a clone launch anything without the person opening it
explicitly consenting. Manually verified the exact spawned command
(`uv run acr mcp serve` under stdio, EOF on stdin) starts and exits
cleanly before committing.

## Codex CLI integration

`.codex/config.toml` at the repo root does the same job as `.mcp.json`
above, for OpenAI's Codex CLI (`codex`) — `[mcp_servers.acr]` with the
identical `uv run acr mcp serve` stdio launch. Verified against a real
installed `codex-cli` (0.137.0), not assumed from docs: secondary sources
disagreed on whether Codex even supports project-scoped MCP config at
all (an open upstream feature request appeared to ask for exactly this),
so this was checked directly rather than trusted. It does — but only for
a project the user has explicitly marked `trust_level = "trusted"` in
their own global `~/.codex/config.toml`; confirmed by creating this file
and running `codex mcp list` from the repo, which did not show `acr`
registered until that trust entry was added. That trust decision governs
more than MCP loading (it affects Codex's sandbox/approval defaults for
the whole project), so this repo does not attempt to grant itself trust —
same boundary as Claude Code's own first-open approval prompt, just
configured on the user's machine instead of interactively per-session.

## PyPI packaging: live

**[`acr-runtime`](https://pypi.org/project/acr-runtime/) is published on
PyPI as of `v0.1.0`** — `pip install acr-runtime` genuinely works; verified
by installing the real published artifact (not a local build) into a
throwaway venv and running `acr version`/`acr db upgrade`/`acr run`
end-to-end against it, same as every other verification this project has
insisted on rather than just asserting.

- **Distribution name is `acr-runtime`, not `acr`.** Checked PyPI before
  assuming the obvious name was free: `acr` is taken (an unrelated,
  abandoned 2011 CMS package), and so are `arc` and `acr-cli`. User chose
  `acr-runtime` from the available options. The installed CLI command
  stays `acr` regardless (`[project.scripts]` is independent of the
  distribution name) — only `pip install <name>` changes.
  `[tool.uv.build-backend] module-name = "acr"` tells uv_build the
  importable module (`src/acr/`) doesn't match the distribution name
  (`acr-runtime` -> `acr_runtime` by default normalization) — without it,
  the build fails looking for a nonexistent `src/acr_runtime/`.
- `pyproject.toml` gained the metadata a real PyPI listing needs:
  `authors`, `keywords`, `classifiers` (honestly "Development Status :: 3
  - Alpha", not overclaiming maturity), and `[project.urls]` pointing at
  the real repo/issues/docs. No `License :: OSI Approved :: MIT License`
  classifier — redundant and deprecated per PEP 639 once `license =
  "MIT"` is set; `uv build` itself warns about the combination.
- **Real bug found by actually building and installing the wheel**, not
  just reading the config: `migrations/` lived at the repo root, outside
  `src/acr/`, so it was never bundled — a `pip install acr-runtime` user
  would have the CLI but no way to create the database schema at all.
  Fixed by moving it to `src/acr/migrations/` (now ships in the wheel;
  `alembic.ini`'s `script_location` updated to match, so the dev/source
  workflow — `uv run alembic upgrade head` — is unaffected) and adding
  `acr.db.migrate.upgrade_to_head()` + `acr db upgrade`: a programmatic
  Alembic runner that builds its own `Config` pointing at the bundled
  migrations directory, needing no `alembic.ini` on disk at all. Both
  paths execute the identical `migrations/env.py`, so behavior can't
  diverge between a dev checkout and an installed package.
- Verified for real, not just asserted: built the wheel, `uv pip
  install`ed it into a throwaway venv, `cd`'d to an unrelated directory
  with no repo, no `alembic.ini`, nothing but the installed package, and
  ran `acr db upgrade` (created a real schema from scratch),
  `acr doctor`, `acr run "..."`, and `acr version` end-to-end — all
  worked identically to the source-checkout experience. Re-ran after the
  `acr` -> `acr-runtime` rename too (that rename briefly broke the local
  dev venv's `acr` console-script shim until `uv sync --reinstall` —
  `uv sync` alone doesn't always regenerate it after a project rename).

### Publishing (Trusted Publishing, no token ever stored)

`.github/workflows/publish.yml` fires on a published GitHub Release and
publishes via [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
(OIDC) — no API token exists anywhere in this repo, in GitHub secrets, or
in this session; verified the exact current setup against PyPI's own docs
rather than guessing. `permissions: id-token: write` at job level plus
`pypa/gh-action-pypi-publish@release/v1` is the whole publish step.

Chosen deliberately over an API-token-based workflow: handling a
token — even one pasted into a GitHub secret rather than given directly
to the assistant — isn't something this session does under any
circumstance. Trusted Publishing needs no token to ever exist.

One-time setup the user did directly (needed their PyPI login, this
session couldn't do it): on pypi.org, Account Settings → Publishing →
added a pending publisher for:

| Field | Value |
|---|---|
| PyPI Project Name | `acr-runtime` |
| Owner | `hbkdad` |
| Repository name | `arc` |
| Workflow filename | `publish.yml` |
| Environment name | `pypi` |

**`v0.1.0` was tagged and released on 2026-07-29**, with the user's
explicit go-ahead (a real, irreversible, public action — a given version
can never be re-uploaded to PyPI once published, so this wasn't done as
an automatic side effect of packaging work). `publish.yml` ran clean —
build, OIDC exchange, upload, attestation generation — and the package
went live in under a minute. Verified against the real, live PyPI
package afterward, not just the workflow's own "success" status.

## Next-level implementations and further-training capabilities (2026-07-29)

A researched, scoped expansion pass — grounded partly in
`hbkdad/Adaptive-Cognitive-Runtime` (a separate, more mature reference
implementation of the same master spec, consulted for design ideas only;
see that repo's own memory note — no code ported, no commits made there)
and partly in real gaps this session found by reading the actual
codebase. Nine additions, each real and tested, none requiring a new
external dependency or touching source/dependencies/permissions (the
proposals scope boundary, unaffected by this pass):

- **`acr.memory.schemas`** — `FailurePayload`/`DecisionPayload` dataclasses
  giving `MemoryType.FAILURE`/`DECISION` a real schema in
  `structured_payload` (a generic JSON column already on `MemoryRecord`)
  instead of free text, plus `remember_failure()`/`remember_decision()`
  write-controller helpers. Parsing is best-effort (`parse_*_payload()`
  returns `None`, never raises, for a pre-schema or free-form record).
- **`acr.learning.failure_intelligence`** — `find_similar_failures()`
  queries `MemoryType.FAILURE` records via the existing hybrid
  `retrieve()` (no new ranking heuristic), filtered to records that
  actually parse as `FailurePayload`. Wired into `acr agents plan`/`spawn`
  (printed, not schema-changing — `AgentSpec`'s docstring commits to "the
  exact field set from master §749-763") and a standalone
  `acr learn failures <objective>`.
- **`acr.learning.consolidation`** — `plan_gc()`/`apply_gc_plan()`, the
  conservative opposite-direction mirror of `promote_candidates()`:
  retires a stale never-graduated `CANDIDATE`, an old `SUPERSEDED`, or an
  old-and-unreviewed `QUARANTINED` record to `ARCHIVED`. `CONFIRMED` is
  never eligible at any age. Two-step by design (`acr memory gc-plan`
  dry-run, `acr memory gc-apply` re-plans and applies) so nothing is ever
  archived as a side effect of just computing a plan; `apply_gc_plan()`
  re-fetches and re-checks each record's status rather than trusting the
  plan's in-memory snapshot, since a real caller might review a plan
  before applying it.
- **`acr.telemetry.explain`** — `explain_task()` replays a task's real
  `TelemetryEvent` trail in order (provider, tokens, computed duration) —
  never a generated narrative. `acr explain <task-id>`. Honest about what
  ACR doesn't retain: `AgentSpec` is an in-memory plan, never persisted,
  so which skills were routed for a given task isn't reconstructable from
  this table alone.
- **`acr.backup`** — `create_backup()`/`restore_backup()`: a zip of
  `Settings.data_dir` (database + `generated_skills/`, not the git-tracked
  `skills/` tree) with a `manifest.json` SHA-256 hash per file.
  `restore_backup()` verifies every hash before writing anything, checks
  every archive member's resolved path stays inside the target directory
  (zip-slip), and refuses a non-empty target unless `force=True`. `acr
  backup create`/`acr backup restore`. Known limitation, documented in the
  module: copies the SQLite file directly rather than using SQLite's own
  online-backup API, so a backup taken during concurrent writes could in
  principle be inconsistent — fine against an idle process, not yet a
  hot-backup tool.
- **`acr.learning.routing_optimization`** — `model_outcomes_for_task_class()`
  computes real per-model success-rate/mean-quality from
  `AgentTopologyRecord` rows (evidence that only exists because of the
  fix below), gated at `min_samples` real recorded runs per model, the
  same discipline `recommend_topology()` already uses.
  `compare_models()` recommends a switch only when a candidate is
  strictly better on *both* dimensions (not just non-regressed — a
  routing change has real cost/risk, unlike a free lateral skill-version
  move). Wired into `proposals.py` as `ProposalKind.ROUTING_OPTIMIZATION`
  (`acr improve propose-routing-optimization <task-class> <current>
  <candidate>`) — **never auto-applies regardless of
  `auto_apply_proposals`**: the only real lever,
  `Settings.default_min_quality_tier`, is an environment variable this
  process must never write to itself, so approving this proposal kind
  means "reviewed by a human," not "applied."
- **Closing the evidence loop** (`acr.agents.factory.spawn_agent()`) — the
  most consequential fix in this pass. `learning.utility.
  record_skill_outcome()` (Phase 8) and `agents.topology.
  record_topology()` (Phase 10) both existed as real, tested functions
  with **nothing in application code ever calling either one** —
  `routing.route()`'s "check prior performance" and
  `recommend_topology()`'s evidence requirement could never see real
  data no matter how many agents actually ran. Fixed at the one choke
  point every caller shares: `spawn_agent()` now reviews its own task and
  records both. `task_class` became a required keyword (threaded through
  `agents_plan`/`agents_spawn`'s new `--task-class`) rather than inferred
  — no classifier model exists, so guessing would silently misattribute
  evidence. `spawn_agent()`'s return type changed from `Task` to
  `tuple[Task, PanelResult]`. Verified with real dogfooding: three `acr
  agents spawn --task-class ui-audit` runs took `acr agents topology
  ui-audit` from "insufficient evidence" to a real recommendation (3/3
  successful, mean quality 1.00), and `dashboard-ui-audit`'s reliability
  moved from `0.00`/0 uses to `1.00`/3 uses on the dashboard's own
  `/skills` page — no seeded rows.
- **MCP `run_task` closes the same loop for external usage**
  (`acr.integrations.mcp_server`) — the MCP tool wrapped
  `core.execution.run_task()` directly, bypassing `spawn_agent()`
  entirely, so real usage from any MCP client (Claude Code, Codex, or
  anything else) never fed the evidence loop even after the fix above.
  `run_task` now accepts an optional `task_class`; when given, it routes
  through `plan_agent()`/`spawn_agent()` (`force=True` — an MCP caller
  isn't opting into the separate cost/risk "worth spawning" gate any more
  than `acr run` is) instead of the bare engine, returning
  `skills_routed`/`review_passed` alongside the existing
  `id`/`objective`/`status`. Omitting `task_class` is byte-for-byte the
  original behavior — existing callers see no change.
- **`acr.learning.self_practice`** — `run_self_practice()` runs every
  active skill's own author-written `applicability` field (not a
  fabricated scenario — the one thing already on record describing when
  the skill should be used) as a real objective for its first declared
  `task_class`, through the same `spawn_agent()` evidence path. `acr
  learn self-practice [--limit N]`. "Scheduled" describes the intended
  use (wire it into cron/Task Scheduler yourself) — this module doesn't
  install anything into the host's own scheduler, a system-level change
  outside what a CLI command does as a side effect.
- **`acr.evaluation.calibration`** — `compute_calibration()`: does stored
  memory `confidence` actually predict outcomes? A fixed-bin reliability
  curve plus a Brier score, computed strictly from
  `successful_uses`/`failed_uses` (the same counters `context.attribution`
  maintains) — a record with zero recorded uses has no empirical outcome
  to compare against and is excluded entirely, never scored as 0%. `acr
  memory calibration`.

One module-organization note worth recording: `self_practice.py` (and
almost `routing_optimization.py`) hit a real circular import —
`acr.agents.factory` imports `acr.learning.utility`, so `acr.learning`'s
own package `__init__.py` can't import anything back from
`acr.agents.factory` at module level without Python finding a partially-
initialized module mid-import. Fixed by deferring `self_practice.py`'s
`agents.factory`/`agents.planner` imports to inside the function body —
standard for this exact class of cycle, and harmless since both packages
are fully loaded by the time the function actually runs.

### Audit pass over the batch above (2026-07-29)

A follow-up review of everything in "Next-level implementations" and the
usage/cost tracking feature above, before considering either done:

- **Confirmed correct, no change needed**: the MCP `run_task` tool's
  `CREDENTIAL_USE` permission/audit gate is checked before the branch on
  `task_class`, so the new evidence-recording path doesn't bypass it.
  `proposals.py`'s `_apply()` for `ROUTING_OPTIMIZATION` is a genuine
  no-op while `approve_proposal()` still records `status=APPROVED` and
  audit-logs for both proposal kinds. `backup.py`'s `restore_backup()`
  verifies every archive member's hash and path safety in a first pass
  before any file is written in a second — never interleaved. A suspected
  zip-slip variant via an absolute-path manifest entry (`pathlib`'s `/`
  operator silently discards the left operand when the right looks
  absolute, so a naive "join then check" could construct a path outside
  `target_dir` without any `..`) turned out to already be caught, because
  `_safe_target()`'s `is_relative_to()` check runs on the *joined result*,
  not by string-inspecting the input — locked in with a new regression
  test, `test_restore_backup_rejects_an_absolute_path_manifest_entry`.
- **Fixed**: several CLI commands (`memory gc-plan`/`gc-apply`,
  `memory calibration`, `learn generate-skills`, `agents topology`,
  `improve propose-routing-optimization`) hardcoded literal default
  values (`30`, `14`, `60`, `1`, `3`) that duplicated named constants
  already defined in the modules they call
  (`acr.learning.consolidation.DEFAULT_*`,
  `acr.evaluation.calibration.DEFAULT_MIN_USES`,
  `acr.learning.skill_generation.DEFAULT_MIN_REPEATS`,
  `acr.agents.topology.DEFAULT_MIN_SAMPLES`,
  `acr.learning.routing_optimization.DEFAULT_MIN_SAMPLES`). Harmless
  today since the literals matched, but a real drift risk: changing a
  module's own default wouldn't have changed what the CLI actually used
  or displayed in `--help`. The CLI now imports and passes through the
  real constants everywhere this pattern appeared.
- **Reviewed, no change needed**: `self_practice.py`'s per-skill loop has
  no `try`/`except` around each `spawn_agent()` call, but that's
  consistent with `spawn_agent()`'s own contract — provider/task failures
  are recorded as a failed outcome and returned, not raised (the same
  property `factory.py`'s `_AlwaysFailsProvider` test already exercises
  for `agents spawn`) — so the loop doesn't need its own handling to
  avoid losing already-completed practice runs to one bad skill.

## What's left

Every phase in the master spec's 15-phase list (§65-66) now has a
smallest-complete-vertical-slice implementation — this is not the same
claim as "the master spec is fully implemented." Real, explicitly
deferred gaps, each with a reason rather than an oversight:

- **Desktop app** (Phase 13, Tauri) — deliberately deferred per explicit
  user decision; large enough to deserve its own scoping conversation
  (target platforms, UI approach) whenever it's picked up.
- ~~PyPI package / "downloads"~~ (Phase 14) — **done.**
  [`acr-runtime`](https://pypi.org/project/acr-runtime/) is live as of
  `v0.1.0` (2026-07-29) — see "PyPI packaging: live" above.
- ~~Bespoke Claude Code / Codex MCP client config~~ (Phase 13) — **done.**
  `.mcp.json` (Claude Code) and `.codex/config.toml` (Codex CLI) both
  register `acr mcp serve` as a project-scoped MCP server, both formats
  verified against real client behavior, not guessed — see "Claude Code
  integration" and "Codex CLI integration" above. Both clients gate
  project-scoped config behind the user's own explicit trust/approval,
  so cloning the repo can't silently launch anything either way.
- ~~Additional self-improvement proposal kinds~~ (Phase 15) — **partially
  done.** `ROUTING_OPTIMIZATION` shipped 2026-07-29 (see "Next-level
  implementations" below) — evidence-gated, advisory-only since there's no
  safe mechanism to auto-apply a routing change. "Strategy optimization"
  and a general "experiments" runner still need their own evidence
  sources; the `Proposal` mechanism itself stayed generic enough that
  adding routing optimization was exactly "a new evidence-producing
  comparison and an `_apply()` branch," confirming that's the real shape
  of a third kind too.
- **Real Ollama/cloud provider usage by default** — reachable (`--min-
  quality-tier`/`min_quality_tier`, `Settings.default_min_quality_tier`
  for a sticky opt-in) and now actually *reliable* when opted into (see
  "Ollama reliability fixes" above — a real, measured availability-check
  and completion-timeout bug, not just a routing gap, previously made
  even an explicit opt-in fail on real hardware). `acr doctor` surfaces
  the opt-in path directly when Ollama is reachable. `0`/mock still stays
  the *out-of-box* default deliberately — a fresh install shouldn't
  silently start making paid API calls or depend on a local daemon being
  up, and this is a documented, tested guarantee scripts/automation can
  rely on. Still a real gap if the goal is "just works with whatever's
  configured, no settings" rather than "one-time opt-in" — that would be
  a product decision about the default itself, not a bug to fix.
- **CI** — done: `.github/workflows/ci.yml` (see "Continuous integration"
  above).

None of the above are "next up" in a committed sequence — they're each a
real, scoped decision waiting on the user (credentials, an account, a
priority call), consistent with the pattern the whole build has followed:
build the smallest real slice of what's asked, name what's deliberately
not built, and never guess at the parts that need someone's actual say-so.
