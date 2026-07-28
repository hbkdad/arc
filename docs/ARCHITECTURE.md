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
├── .github/workflows/ci.yml  # ruff + pyright + migrations + pytest, every push/PR
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
assumed. `spawn_agent()` itself is a thin, honest wrapper: it calls the
real `run_task()` (Phase 1) with the spec's provider and objective; no
parallel "fake execution" path exists.

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
uv run acr agents plan "objective" [--task-class X]        # AgentSpec via real routing + exposure
uv run acr agents spawn "objective" [--force]               # estimate -> run_task() -> critic review
uv run acr agents topology <task-class>                     # evidence-gated worker-count recommendation
uv run acr dashboard serve [--host --port]   # dashboard + /visualization: http://127.0.0.1:8765
uv run acr mcp serve [--transport stdio|sse|streamable-http] [--host --port]
uv run acr improve propose-skill-evolution <baseline-id> <candidate-id>
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

Memory *writing* is still library-level only (`acr.memory.write_controller`,
plus `acr.learning.distillation` as a real caller) — no
`acr memory remember ...` CLI verb for arbitrary facts yet.

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
(`mcpServers.<name>.{type,command,args}`; verified rather than guessed,
unlike the Codex-side gap noted above). Deliberately has **no** hardcoded
absolute path in `args` — a public repo's `.mcp.json` travels with every
clone, and Claude Code spawns the server with its working directory set
to wherever the project actually is, so hardcoding this machine's path
would silently break for anyone else. Claude Code prompts for approval
the first time a project with a `.mcp.json` opens (`⏸ Pending approval`
until then), so committing this file can't make a clone launch anything
without the person opening it explicitly consenting. Manually verified
the exact spawned command (`uv run acr mcp serve` under stdio, EOF on
stdin) starts and exits cleanly before committing.

## PyPI packaging groundwork

Not published yet (needs a PyPI account/token from the user — a distinct
action, not assumed here), but the package now builds and actually works
standalone, which a real `uv build` + install test caught two gaps in:

- `pyproject.toml` gained the metadata a real PyPI listing needs:
  `authors`, `keywords`, `classifiers` (honestly "Development Status :: 3
  - Alpha", not overclaiming maturity), and `[project.urls]` pointing at
  the real repo/issues/docs. No `License :: OSI Approved :: MIT License`
  classifier — redundant and deprecated per PEP 639 once `license =
  "MIT"` is set; `uv build` itself warns about the combination.
- **Real bug found by actually building and installing the wheel**, not
  just reading the config: `migrations/` lived at the repo root, outside
  `src/acr/`, so it was never bundled — a `pip install acr` user would
  have the CLI but no way to create the database schema at all.
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
  `acr doctor`, and `acr run "..."` end-to-end — all worked identically
  to the source-checkout experience.

## What's left

Every phase in the master spec's 15-phase list (§65-66) now has a
smallest-complete-vertical-slice implementation — this is not the same
claim as "the master spec is fully implemented." Real, explicitly
deferred gaps, each with a reason rather than an oversight:

- **Desktop app** (Phase 13, Tauri) — deliberately deferred per explicit
  user decision; large enough to deserve its own scoping conversation
  (target platforms, UI approach) whenever it's picked up.
- **PyPI package / "downloads"** (Phase 14) — packaging groundwork done
  and verified working (build + install + run end-to-end in an isolated
  environment — see "PyPI packaging groundwork" above); actually
  publishing needs a PyPI account/token from the user, not assumed here.
- **Bespoke Claude Code / Codex MCP client config** (Phase 13) — half
  done. `.mcp.json` at the repo root registers `acr mcp serve` as a
  project-scoped MCP server for Claude Code specifically (format
  verified against current documentation, not guessed — see "Claude Code
  integration" below); Claude Code prompts for approval the first time a
  project opens with it, so cloning the repo can't silently launch
  anything. Codex's equivalent config format is still unverified and
  intentionally not built.
- **Additional self-improvement proposal kinds** (Phase 15) — "strategy
  optimization," "routing optimization," and a general "experiments"
  runner all need their own evidence sources before they could honestly
  propose anything; none of those evidence sources exist yet. The
  `Proposal` mechanism itself is generic (see "Controlled
  self-improvement" above) — a second proposal kind is a matter of
  writing a new evidence-producing comparison and an `_apply()` branch,
  not a redesign.
- **Real Ollama/cloud provider usage by default** — fixed to be reachable
  (see "Real provider routing" above: `--min-quality-tier`/`min_quality_tier`
  now actually route there), but `0`/mock stays the *default* deliberately
  — a fresh install shouldn't silently start making paid API calls or
  depend on a local daemon being up. Still a real gap if the goal is
  "just works with whatever's configured" rather than "opt-in."
- **CI** — done: `.github/workflows/ci.yml` (see "Continuous integration"
  above).
- **PyPI packaging groundwork** — not started. Needed for the "individual
  developers" go-to-market audience to get `pip install acr`/`uvx acr`
  instead of clone + `uv sync`; actually publishing needs a PyPI
  account/token from the user.

None of the above are "next up" in a committed sequence — they're each a
real, scoped decision waiting on the user (credentials, an account, a
priority call), consistent with the pattern the whole build has followed:
build the smallest real slice of what's asked, name what's deliberately
not built, and never guess at the parts that need someone's actual say-so.
