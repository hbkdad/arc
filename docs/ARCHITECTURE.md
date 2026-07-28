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

## Current shape (Phase 0 Foundation + Phase 1 Execution + Phase 2 Memory + Phase 3 Context + Phase 4 Skills + Phase 5 Evaluation + Phase 6 Routing + Phase 7 Security + Phase 8 Learning + Phase 9 Skill Evolution)

Only the Python CLI foundation, task engine, memory system, context compiler,
skill system, evaluation system, model/tool routing, security layer,
learning system, and skill validation/evolution exist. See
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
│       ├── 87b619c4e7ac_task_engine_and_telemetry_tables.py
│       ├── 6c384104b66a_memory_records_and_fts5.py
│       ├── 83b4d32aa8f2_skills_registry_and_fts5.py
│       └── 5a8d4f37fff6_benchmark_runs.py
├── src/acr/
│   ├── __init__.py        # __version__
│   ├── config.py          # Settings (pydantic-settings, ACR_* env / .env)
│   ├── logging.py         # structlog JSON/console setup
│   ├── db/
│   │   ├── __init__.py
│   │   └── base.py        # async SQLAlchemy engine/session, Base
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
│   │   ├── default_tools.py    # real tools: memory_search, skill_search
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
│   └── learning/
│       ├── distillation.py     # distill_task()/distill_and_remember(): trace -> memory candidate
│       ├── utility.py          # record_skill_outcome(): SkillRecord successful_uses/reliability
│       ├── promotion.py        # promote_candidates(): CANDIDATE -> CONFIRMED on earned utility
│       └── skill_generation.py # detect_repeated_successes()/generate_candidate_skill()
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
│   ├── test_skill_validation.py
│   └── test_skill_evolution.py
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
is `acr.routing.models` — see Phase 6 below.

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

## Commands available today

```bash
uv run acr doctor              # Python version, data dir, DB, mock + Ollama providers
uv run acr version
uv run acr run "objective"     # create + execute a Task end-to-end via the mock provider
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
uv run alembic upgrade head
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

Memory *writing* is still library-level only (`acr.memory.write_controller`,
plus `acr.learning.distillation` as a real caller) — no
`acr memory remember ...` CLI verb for arbitrary facts yet.

## Next milestone

Phase 10 — Agents: agent specification, factory, planner, critic, topology
history (master §747-793).
