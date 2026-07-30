"""ACR command-line interface (master spec §61).

Every subcommand is a thin wrapper over a real, tested module elsewhere in
`acr` — this file wires Typer arguments to those functions and formats
their output; it holds no business logic of its own. See
docs/ARCHITECTURE.md's command reference for the full, current list.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer

from acr import __version__
from acr.agents.factory import SpawnNotWorthwhileError, estimate_spawn, spawn_agent
from acr.agents.models import AgentSpec, SpawnEstimate
from acr.agents.planner import plan_agent
from acr.agents.topology import (
    DEFAULT_MIN_SAMPLES as DEFAULT_TOPOLOGY_MIN_SAMPLES,
)
from acr.agents.topology import TopologyRecommendation, recommend_topology
from acr.backup import (
    BackupIntegrityError,
    RestoreTargetNotEmptyError,
    UnsafeArchiveMemberError,
    create_backup,
    restore_backup,
)
from acr.benchmarks import memory_recall
from acr.benchmarks.models import BenchmarkRun
from acr.benchmarks.runner import run_suite
from acr.config import get_settings
from acr.context.compiler import compile_context
from acr.context.models import ContextBundle
from acr.core.execution import run_task
from acr.core.tasks.models import Task, TaskStatus
from acr.dashboard.app import create_app as create_dashboard_app
from acr.db.base import session_scope
from acr.db.migrate import upgrade_to_head
from acr.doctor import CheckStatus, run_checks
from acr.evaluation.calibration import DEFAULT_MIN_USES, CalibrationReport, compute_calibration
from acr.evaluation.evaluators import ExactMatchEvaluator
from acr.evaluation.panel import PanelResult
from acr.evaluation.regression import RegressionReport, detect_regression
from acr.evaluation.waste_analyzer import (
    DuplicateGroup,
    UtilizationReport,
    analyze_context_utilization,
    find_duplicate_memories,
)
from acr.integrations.mcp_server import create_mcp_server
from acr.learning.consolidation import (
    DEFAULT_QUARANTINED_RETENTION_DAYS,
    DEFAULT_STALE_CANDIDATE_DAYS,
    DEFAULT_SUPERSEDED_RETENTION_DAYS,
    GCPlan,
    apply_gc_plan,
    plan_gc,
)
from acr.learning.distillation import DistillationResult, TaskNotFoundError, distill_and_remember
from acr.learning.failure_intelligence import SimilarFailure, find_similar_failures
from acr.learning.promotion import PromotionReport, promote_candidates
from acr.learning.proposals import (
    Proposal,
    ProposalNotFoundError,
    ProposalNotPendingError,
    ProposalStatus,
    SelfImprovementDisabledError,
    approve_proposal,
    list_proposals,
    propose_routing_optimization,
    propose_skill_evolution,
    reject_proposal,
)
from acr.learning.routing_optimization import (
    DEFAULT_MIN_SAMPLES as DEFAULT_ROUTING_MIN_SAMPLES,
)
from acr.learning.routing_optimization import model_outcomes_for_task_class
from acr.learning.self_practice import PracticeRun, run_self_practice
from acr.learning.skill_generation import (
    DEFAULT_MIN_REPEATS,
    RepeatedPattern,
    detect_repeated_successes,
    generate_candidate_skill,
)
from acr.logging import configure_logging, get_logger
from acr.memory.git_ingest import GitCommandError, record_commit_as_decision
from acr.memory.models import MemoryRecord
from acr.memory.write_controller import WriteEvaluation
from acr.providers.base import CompletionRequest
from acr.providers.mock import MockProvider
from acr.routing.models import (
    ModelProfile,
    NoProviderAvailableError,
    RoutedCompletion,
    build_default_router,
)
from acr.security.audit import recent_audit_events
from acr.security.injection import scan_for_injection
from acr.security.permissions import Capability, PermissionDeniedError, PermissionSet
from acr.security.safe_mode import SafeModeError
from acr.skills.evolution import (
    EvolutionComparison,
    compare_versions,
    create_candidate_version,
    promote_evolution,
    rollback_evolution,
)
from acr.skills.models import InvalidSkillTransition, SkillRecord, SkillStatus
from acr.skills.registry import SkillNotFoundError, get, list_skills, register, set_status
from acr.skills.routing import RoutedSkill, route
from acr.skills.search import SkillSearchResult, search
from acr.skills.validation import ValidationReport, run_validation
from acr.telemetry.explain import TaskExplanation, explain_task
from acr.telemetry.explain import TaskNotFoundError as TaskExplainNotFoundError
from acr.telemetry.models import TelemetryEvent
from acr.telemetry.recorder import TelemetryRecorder
from acr.telemetry.usage import ProviderUsage, usage_by_provider
from acr.tools.browser import BrowserNotInstalledError
from acr.tools.default_tools import build_default_registry
from acr.tools.exposure import expose_tools
from acr.tools.github_search import GhCliError, GhCliNotFoundError, GhCliTimeoutError
from acr.tools.invocation import invoke_tool
from acr.tools.models import ToolSpec
from acr.tools.registry import ToolNotFoundError
from acr.tools.web_fetch import InvalidUrlError

app = typer.Typer(name="acr", help="ACR — Adaptive Cognitive Runtime", no_args_is_help=True)
context_app = typer.Typer(name="context", help="Context compiler operations.")
skills_app = typer.Typer(name="skills", help="Skill registry operations.")
benchmark_app = typer.Typer(name="benchmark", help="Benchmark suites.")
waste_app = typer.Typer(name="waste", help="Token waste analysis.")
models_app = typer.Typer(name="models", help="Model routing.")
tools_app = typer.Typer(name="tools", help="Tool registry operations.")
security_app = typer.Typer(name="security", help="Security: audit log, injection scanning.")
learn_app = typer.Typer(name="learn", help="Experience distillation, promotion, skill generation.")
agents_app = typer.Typer(name="agents", help="Agent planning, spawning, review, topology history.")
dashboard_app = typer.Typer(name="dashboard", help="Operational dashboard.")
mcp_app = typer.Typer(name="mcp", help="MCP server exposure.")
improve_app = typer.Typer(name="improve", help="Controlled self-improvement proposals.")
db_app = typer.Typer(name="db", help="Database schema management.")
memory_app = typer.Typer(
    name="memory", help="Memory lifecycle: consolidation and garbage collection."
)
backup_app = typer.Typer(name="backup", help="Backup and restore the local data directory.")
app.add_typer(context_app)
app.add_typer(skills_app)
app.add_typer(benchmark_app)
app.add_typer(waste_app)
app.add_typer(learn_app)
app.add_typer(models_app)
app.add_typer(tools_app)
app.add_typer(security_app)
app.add_typer(agents_app)
app.add_typer(dashboard_app)
app.add_typer(mcp_app)
app.add_typer(improve_app)
app.add_typer(db_app)
app.add_typer(memory_app)
app.add_typer(backup_app)

# Every registered benchmark suite: name -> (seed, build_cases). Only one
# exists today (master principle #23: no feature expansion without
# something real to measure) — more land as the subsystems they benchmark do.
_BENCHMARK_SUITES = {
    memory_recall.SUITE_NAME: (memory_recall.seed, memory_recall.build_cases),
}

_STATUS_SYMBOL = {
    CheckStatus.OK: "[OK]  ",
    CheckStatus.WARN: "[WARN]",
    CheckStatus.FAIL: "[FAIL]",
}


@app.callback()
def main() -> None:
    configure_logging(get_settings())


@app.command()
def version() -> None:
    """Print the installed ACR version."""
    typer.echo(__version__)


@app.command()
def doctor() -> None:
    """Run local environment health checks (Python version, data dir, database)."""
    logger = get_logger("acr.doctor")
    settings = get_settings()
    results = asyncio.run(run_checks(settings))

    exit_code = 0
    for result in results:
        typer.echo(f"{_STATUS_SYMBOL[result.status]} {result.name}: {result.detail}")
        logger.info(
            "doctor.check",
            check=result.name,
            status=result.status.value,
            detail=result.detail,
        )
        if result.status is CheckStatus.FAIL:
            exit_code = 1

    raise typer.Exit(code=exit_code)


@app.command()
def setup() -> None:
    """Interactive first-run wizard: create .env if missing, optionally
    configure cloud provider API keys, then re-run doctor to confirm.

    Installation is already one command (`pip install acr-runtime` /
    `uv tool install acr-runtime`); this covers the one part that can't
    be scripted away without a real security downside -- an API key only
    its owner can supply. Every key you enter here is typed directly into
    *your own* terminal (masked when run in a real interactive terminal)
    and written only to your local .env; this command never transmits it
    anywhere. Skip any provider you don't want -- ACR runs fully
    local-first with none of them configured (master principle #2:
    cloud-optional)."""
    env_path = Path(".env")
    if not env_path.exists():
        example = Path(".env.example")
        env_path.write_text(
            example.read_text(encoding="utf-8") if example.exists() else "",
            encoding="utf-8",
        )
        typer.echo(f"created {env_path.resolve()}")
    else:
        typer.echo(f"found {env_path.resolve()}")

    existing = env_path.read_text(encoding="utf-8")

    def has_var(var: str) -> bool:
        for line in existing.splitlines():
            stripped = line.strip()
            if stripped.startswith(f"{var}=") and stripped[len(var) + 1 :]:
                return True
        return False

    def append_var(var: str, value: str) -> None:
        nonlocal existing
        with env_path.open("a", encoding="utf-8") as f:
            f.write(f"\n{var}={value}\n")
        existing += f"\n{var}={value}\n"

    def configure_provider(var: str, label: str, console_url: str) -> None:
        if has_var(var):
            typer.echo(f"{label}: already configured in .env, skipping")
            return
        if not typer.confirm(f"Configure {label}? (get a key at {console_url})", default=False):
            typer.echo(f"{label}: skipped -- ACR runs fully local-first without it")
            return
        # hide_input=True reads via the OS's own masked-input mechanism
        # (getpass), which expects a real console -- piped/non-interactive
        # stdin (scripted setup, CI, this command run inside another tool)
        # has no console for it to read from and hangs forever waiting for
        # keystrokes that will never come, rather than erroring. Only take
        # that path when stdin is actually a terminal; otherwise read
        # plainly (unmasked, but functional) and say so up front.
        if sys.stdin.isatty():
            key = typer.prompt(f"{label} API key", hide_input=True).strip()
        else:
            typer.echo("(non-interactive input detected -- the key won't be masked as you type)")
            key = typer.prompt(f"{label} API key").strip()
        if not key:
            typer.echo(f"{label}: empty input, skipping")
            return
        append_var(var, key)
        typer.echo(f"{label}: written to .env")

    configure_provider(
        "ACR_ANTHROPIC_API_KEY", "Anthropic (Claude)", "https://console.anthropic.com/settings/keys"
    )
    configure_provider("ACR_OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys")

    cloud_configured = has_var("ACR_ANTHROPIC_API_KEY") or has_var("ACR_OPENAI_API_KEY")
    ask_default_tier = cloud_configured and not has_var("ACR_DEFAULT_MIN_QUALITY_TIER")
    if ask_default_tier and typer.confirm(
        "Route `acr run`/MCP `run_task` through a configured provider by "
        "default instead of only the free mock/Ollama tiers? "
        "(--min-quality-tier still overrides this per-call either way)",
        default=False,
    ):
        append_var("ACR_DEFAULT_MIN_QUALITY_TIER", "2")
        typer.echo("default_min_quality_tier: set to 2 in .env")

    typer.echo("\nre-checking (a fresh process, since .env is only read at startup)...")
    settings = get_settings()
    results = asyncio.run(run_checks(settings))
    for result in results:
        typer.echo(f"{_STATUS_SYMBOL[result.status]} {result.name}: {result.detail}")


@app.command()
def run(
    objective: str = typer.Argument(..., help="Objective for the task engine to execute."),
    min_quality_tier: int | None = typer.Option(
        None,
        "--min-quality-tier",
        help="0=mock only, no cost. Raise to prefer a configured Ollama/cloud "
        "provider via the routing ladder (Phase 6). Defaults to "
        "Settings.default_min_quality_tier (ACR_DEFAULT_MIN_QUALITY_TIER, "
        "itself 0 unless set) when omitted.",
    ),
) -> None:
    """Create and execute a task end to end (task engine + provider + telemetry).

    Provider selection goes through the same routing ladder as
    `acr models route`: cheapest-qualified-and-available wins. At the
    out-of-box default (tier 0), that's always the zero-config mock
    provider (always available) -- identical behavior to before
    --min-quality-tier existed, so existing scripts/automation aren't
    affected. Raising the tier -- per-call via this flag, or persistently
    via ACR_DEFAULT_MIN_QUALITY_TIER -- opts into real Ollama/cloud usage
    if configured.
    """
    logger = get_logger("acr.cli.run")
    settings = get_settings()
    router = build_default_router(settings)
    resolved_tier = (
        min_quality_tier if min_quality_tier is not None else (settings.default_min_quality_tier)
    )

    async def _run() -> Task:
        profile = await router.select(min_quality_tier=resolved_tier)
        async with session_scope(settings) as session:
            return await run_task(session, objective, profile.provider, TelemetryRecorder())

    try:
        task = asyncio.run(_run())
    except NoProviderAvailableError as exc:
        typer.echo(f"no provider available: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"task {task.id} -> {task.status.value}")
    logger.info("cli.run.completed", task_id=task.id, status=task.status.value)

    if task.status is TaskStatus.FAILED:
        raise typer.Exit(code=1)


@app.command()
def explain(task_id: str = typer.Argument(..., help="Task id to explain.")) -> None:
    """Replay a task's real telemetry trail: what happened, in order, and
    what it retained -- never a generated narrative (see docs/ARCHITECTURE.md)."""
    settings = get_settings()

    async def _explain() -> TaskExplanation:
        async with session_scope(settings) as session:
            return await explain_task(session, task_id)

    try:
        explanation = asyncio.run(_explain())
    except TaskExplainNotFoundError as exc:
        typer.echo(f"unknown task: {exc}")
        raise typer.Exit(code=1) from exc

    task = explanation.task
    typer.echo(f"{task.id}\t{task.objective!r}\t{task.status.value}")
    if explanation.provider:
        typer.echo(f"provider: {explanation.provider}")
    if explanation.output_tokens is not None:
        typer.echo(f"output_tokens: {explanation.output_tokens}")
    if explanation.duration_seconds is not None:
        typer.echo(f"duration: {explanation.duration_seconds:.3f}s")
    if not explanation.events:
        typer.echo("no telemetry events recorded for this task")
        return
    typer.echo("timeline:")
    for event in explanation.events:
        typer.echo(f"  {event.created_at.isoformat()}  {event.event_type}\t{event.payload}")


@context_app.command("compile")
def context_compile(
    objective: str = typer.Argument(..., help="Task objective to compile context for."),
    budget: int = typer.Option(2000, "--budget", help="Token budget for the compiled bundle."),
) -> None:
    """Compile a context bundle from memory for a given objective."""
    settings = get_settings()

    async def _compile() -> ContextBundle:
        async with session_scope(settings) as session:
            bundle = await compile_context(session, task_objective=objective, token_budget=budget)
            await session.commit()
            return bundle

    bundle = asyncio.run(_compile())
    typer.echo(f"bundle: {len(bundle.items)} items, {bundle.total_tokens}/{budget} tokens")
    for item in bundle.items:
        typer.echo(
            f"  [{item.source.value}] {item.id[:8]} relevance={item.relevance:.2f} "
            f"tokens={item.token_cost} — {item.selection_reason}"
        )


@skills_app.command("register")
def skills_register(
    path: Path = typer.Argument(
        ..., help="Path to a skill package directory (contains SKILL.yaml)."
    ),
) -> None:
    """Register (or re-register) a skill package from disk."""
    settings = get_settings()

    async def _register() -> SkillRecord:
        async with session_scope(settings) as session:
            record = await register(session, path)
            await session.commit()
            return record

    record = asyncio.run(_register())
    typer.echo(f"{record.id} v{record.version} -> {record.status.value}")


@skills_app.command("list")
def skills_list(
    status: SkillStatus | None = typer.Option(None, "--status", help="Filter by status."),
) -> None:
    """List registered skills."""
    settings = get_settings()

    async def _list() -> list[SkillRecord]:
        async with session_scope(settings) as session:
            return await list_skills(session, status=status)

    for record in asyncio.run(_list()):
        typer.echo(f"{record.id}\tv{record.version}\t{record.status.value}\t{record.name}")


@skills_app.command("search")
def skills_search(
    query: str = typer.Argument(..., help="Keyword search over skill name/description."),
) -> None:
    """Search the skill registry."""
    settings = get_settings()

    async def _search() -> list[SkillSearchResult]:
        async with session_scope(settings) as session:
            return await search(session, query)

    for result in asyncio.run(_search()):
        typer.echo(f"{result.record.id}\trank={result.rank:.2f}\t{result.record.description}")


@skills_app.command("activate")
def skills_activate(
    skill_id: str = typer.Argument(..., help="Skill id to transition."),
    status: SkillStatus = typer.Option(
        SkillStatus.ACTIVE, "--status", help="Target status (manual activation, master §696)."
    ),
) -> None:
    """Manually transition a skill's lifecycle status."""
    settings = get_settings()

    async def _set_status() -> SkillRecord:
        async with session_scope(settings) as session:
            record = await set_status(session, skill_id, status, safe_mode=settings.safe_mode)
            await session.commit()
            return record

    try:
        record = asyncio.run(_set_status())
    except SkillNotFoundError as exc:
        typer.echo(f"unknown skill: {exc}")
        raise typer.Exit(code=1) from exc
    except (SafeModeError, InvalidSkillTransition) as exc:
        typer.echo(f"denied: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"{record.id} -> {record.status.value}")


@skills_app.command("route")
def skills_route(
    objective: str = typer.Argument(..., help="Task description to route to active skills."),
    task_class: str | None = typer.Option(None, "--task-class"),
) -> None:
    """Route a task to the smallest useful set of active skills."""
    settings = get_settings()

    async def _route() -> list[RoutedSkill]:
        async with session_scope(settings) as session:
            return await route(session, objective, task_class=task_class)

    for routed in asyncio.run(_route()):
        typer.echo(f"{routed.record.id}\t{routed.selection_reason}")


@benchmark_app.command("run")
def benchmark_run(
    suite: str = typer.Argument(..., help="Benchmark suite name (e.g. memory-recall)."),
) -> None:
    """Run a benchmark suite for real and persist the result."""
    if suite not in _BENCHMARK_SUITES:
        typer.echo(f"unknown suite {suite!r}; available: {', '.join(_BENCHMARK_SUITES)}")
        raise typer.Exit(code=1)
    seed_fn, build_cases_fn = _BENCHMARK_SUITES[suite]
    settings = get_settings()

    async def _run() -> BenchmarkRun:
        async with session_scope(settings) as session:
            await seed_fn(session)
            cases = build_cases_fn(session)
            benchmark_run_record = await run_suite(session, suite, cases, ExactMatchEvaluator())
            await session.commit()
            return benchmark_run_record

    result = asyncio.run(_run())
    typer.echo(
        f"{result.suite_name}: {result.passed_cases}/{result.total_cases} passed, "
        f"score={result.score:.2f}"
    )
    if result.passed_cases < result.total_cases:
        raise typer.Exit(code=1)


@benchmark_app.command("history")
def benchmark_history(
    suite: str = typer.Argument(..., help="Benchmark suite name."),
) -> None:
    """Compare the two most recent runs of a suite and report regression."""
    settings = get_settings()

    async def _history() -> RegressionReport:
        async with session_scope(settings) as session:
            return await detect_regression(session, suite)

    report = asyncio.run(_history())
    typer.echo(report.detail)
    if report.regressed:
        raise typer.Exit(code=1)


@waste_app.command("duplicates")
def waste_duplicates() -> None:
    """List memory content duplicated across different subjects."""
    settings = get_settings()

    async def _duplicates() -> list[DuplicateGroup]:
        async with session_scope(settings) as session:
            return await find_duplicate_memories(session)

    groups = asyncio.run(_duplicates())
    if not groups:
        typer.echo("no duplicate memory content found")
        return
    for group in groups:
        typer.echo(f"{len(group.record_ids)}x  {group.content[:80]!r}")


@waste_app.command("utilization")
def waste_utilization() -> None:
    """Report what fraction of compiled context tokens actually got used."""
    settings = get_settings()

    async def _utilization() -> UtilizationReport:
        async with session_scope(settings) as session:
            return await analyze_context_utilization(session)

    report = asyncio.run(_utilization())
    typer.echo(
        f"samples={report.sample_count} utilization={report.utilization:.2%} "
        f"wasted_tokens={report.wasted_tokens}"
    )


@models_app.command("list")
def models_list() -> None:
    """List the model routing ladder and each profile's live availability."""
    settings = get_settings()
    router = build_default_router(settings)

    async def _availability() -> list[tuple[ModelProfile, bool]]:
        return [(p, await p.provider.is_available()) for p in router.profiles]

    for profile, available in asyncio.run(_availability()):
        status = "available" if available else "unavailable"
        typer.echo(
            f"{profile.name}\ttier={profile.quality_tier}\t"
            f"cost/1k={profile.cost_per_1k_tokens:.2f}\t{status}"
        )


@models_app.command("route")
def models_route(
    prompt: str = typer.Argument(..., help="Prompt to complete via the routed model ladder."),
    min_quality_tier: int = typer.Option(0, "--min-quality-tier"),
) -> None:
    """Complete a prompt via the cheapest qualifying available model."""
    settings = get_settings()
    router = build_default_router(settings)

    async def _route() -> RoutedCompletion:
        return await router.complete_with_escalation(
            CompletionRequest(prompt=prompt), min_quality_tier=min_quality_tier
        )

    try:
        routed = asyncio.run(_route())
    except NoProviderAvailableError as exc:
        typer.echo(f"no provider available: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"tried={','.join(routed.tried_profiles)} escalated={routed.escalated}")
    typer.echo(routed.result.text)


@models_app.command("usage")
def models_usage() -> None:
    """Real per-provider call counts, tokens, and estimated cost, from
    every recorded model.call.completed event -- cost uses each
    provider's *current* cost_per_1k_tokens, not a historical price
    catalog (there isn't one), applied to all-time usage."""
    settings = get_settings()
    router = build_default_router(settings)

    async def _usage() -> list[ProviderUsage]:
        async with session_scope(settings) as session:
            return await usage_by_provider(session, router.profiles)

    usage = asyncio.run(_usage())
    if not usage:
        typer.echo("no model calls recorded yet")
        return
    for u in usage:
        cost = f"{u.estimated_cost:.4f}" if u.estimated_cost is not None else "unknown"
        typer.echo(
            f"{u.provider}\tcalls={u.call_count}\t"
            f"input_tokens={u.input_tokens}\toutput_tokens={u.output_tokens}\t"
            f"estimated_cost={cost}"
        )


@tools_app.command("list")
def tools_list() -> None:
    """List every registered tool."""
    registry = build_default_registry()
    for tool in registry.list_tools():
        typer.echo(f"{tool.name}\t{tool.side_effect_level.value}\t{tool.description}")


@tools_app.command("expose")
def tools_expose(
    task_description: str = typer.Argument(..., help="Task to expose relevant tools for."),
    max_tools: int = typer.Option(5, "--max-tools"),
) -> None:
    """Show the task-specific subset of tools that would be exposed to a model."""
    registry = build_default_registry()
    exposed: list[ToolSpec] = expose_tools(registry, task_description, max_tools=max_tools)
    if not exposed:
        typer.echo("no tools matched this task description")
        return
    for tool in exposed:
        typer.echo(f"{tool.name}\t{tool.description}")


# The CLI operator's own local session: full read access to ACR's own
# read-only tools. memory_search/skill_search/web_fetch only need these
# three capabilities (see each ToolSpec.permissions in default_tools.py).
_CLI_OPERATOR_GRANTS = PermissionSet(
    granted=frozenset({Capability.MEMORY_READ, Capability.SKILL_READ, Capability.NETWORK_READ})
)


@tools_app.command("invoke")
def tools_invoke(
    name: str = typer.Argument(..., help="Registered tool name, e.g. memory_search."),
    query: str = typer.Option(..., "--query", help="Query argument passed to the tool."),
    limit: int = typer.Option(5, "--limit"),
) -> None:
    """Invoke a registered tool for real, through permission + safe-mode checks."""
    settings = get_settings()
    registry = build_default_registry()

    async def _invoke() -> object:
        async with session_scope(settings) as session:
            result = await invoke_tool(
                session,
                registry,
                name,
                grants=_CLI_OPERATOR_GRANTS,
                telemetry=TelemetryRecorder(),
                safe_mode=settings.safe_mode,
                query=query,
                limit=limit,
            )
            await session.commit()
            return result

    try:
        result = asyncio.run(_invoke())
    except ToolNotFoundError as exc:
        typer.echo(f"unknown tool: {exc}")
        raise typer.Exit(code=1) from exc
    except (PermissionDeniedError, SafeModeError) as exc:
        typer.echo(f"denied: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(result)


@tools_app.command("fetch")
def tools_fetch(
    url: str = typer.Argument(..., help="http(s) URL to fetch."),
    max_chars: int = typer.Option(4000, "--max-chars"),
) -> None:
    """Fetch a URL and print its extracted text (master §1707-1713, browser automation)."""
    settings = get_settings()
    registry = build_default_registry()

    async def _fetch() -> object:
        async with session_scope(settings) as session:
            result = await invoke_tool(
                session,
                registry,
                "web_fetch",
                grants=_CLI_OPERATOR_GRANTS,
                telemetry=TelemetryRecorder(),
                safe_mode=settings.safe_mode,
                url=url,
                max_chars=max_chars,
            )
            await session.commit()
            return result

    try:
        result = asyncio.run(_fetch())
    except InvalidUrlError as exc:
        typer.echo(f"invalid url: {exc}")
        raise typer.Exit(code=1) from exc
    except (PermissionDeniedError, SafeModeError) as exc:
        typer.echo(f"denied: {exc}")
        raise typer.Exit(code=1) from exc

    assert isinstance(result, dict)
    if result["suspicious"]:
        typer.echo(f"[WARN] suspicious content detected: {result['matched_patterns']}")
    truncated_note = " [truncated]" if result["truncated"] else ""
    typer.echo(f"{result['url']} ({result['status_code']}){truncated_note}")
    typer.echo(result["text"])


@tools_app.command("github-search")
def tools_github_search(
    query: str = typer.Argument(..., help='GitHub search query, e.g. "repo:owner/name is:pr".'),
    limit: int = typer.Option(5, "--limit"),
) -> None:
    """Search GitHub issues/PRs, read-only, via the already-authenticated gh CLI."""
    settings = get_settings()
    registry = build_default_registry()

    async def _search() -> object:
        async with session_scope(settings) as session:
            result = await invoke_tool(
                session,
                registry,
                "github_search",
                grants=_CLI_OPERATOR_GRANTS,
                telemetry=TelemetryRecorder(),
                safe_mode=settings.safe_mode,
                query=query,
                limit=limit,
            )
            await session.commit()
            return result

    try:
        result = asyncio.run(_search())
    except GhCliNotFoundError as exc:
        typer.echo(f"gh not available: {exc}")
        raise typer.Exit(code=1) from exc
    except (GhCliError, GhCliTimeoutError) as exc:
        typer.echo(f"gh api failed: {exc}")
        raise typer.Exit(code=1) from exc
    except (PermissionDeniedError, SafeModeError) as exc:
        typer.echo(f"denied: {exc}")
        raise typer.Exit(code=1) from exc

    assert isinstance(result, list)
    if not result:
        typer.echo("no results")
        return
    for item in result:
        flag = " [SUSPICIOUS]" if item["suspicious"] else ""
        kind = "PR" if item["is_pull_request"] else "issue"
        typer.echo(f"{item['repository']}#{item['number']} ({kind}, {item['state']}){flag}")
        typer.echo(f"  {item['title']}")
        typer.echo(f"  {item['url']}")


@tools_app.command("browse")
def tools_browse(
    url: str = typer.Argument(..., help="http(s) URL to render in a real headless browser."),
    max_chars: int = typer.Option(4000, "--max-chars"),
) -> None:
    """Render a URL and print its visible text, including JS-rendered content."""
    settings = get_settings()
    registry = build_default_registry()

    async def _browse() -> object:
        async with session_scope(settings) as session:
            result = await invoke_tool(
                session,
                registry,
                "browser_fetch",
                grants=_CLI_OPERATOR_GRANTS,
                telemetry=TelemetryRecorder(),
                safe_mode=settings.safe_mode,
                url=url,
                max_chars=max_chars,
            )
            await session.commit()
            return result

    try:
        result = asyncio.run(_browse())
    except InvalidUrlError as exc:
        typer.echo(f"invalid url: {exc}")
        raise typer.Exit(code=1) from exc
    except BrowserNotInstalledError as exc:
        typer.echo(f"browser not installed: {exc}")
        raise typer.Exit(code=1) from exc
    except (PermissionDeniedError, SafeModeError) as exc:
        typer.echo(f"denied: {exc}")
        raise typer.Exit(code=1) from exc

    assert isinstance(result, dict)
    if result["suspicious"]:
        typer.echo(f"[WARN] suspicious content detected: {result['matched_patterns']}")
    truncated_note = " [truncated]" if result["truncated"] else ""
    typer.echo(f"{result['title']} — {result['url']} ({result['status_code']}){truncated_note}")
    typer.echo(result["text"])


@app.command("safe-mode")
def safe_mode_status() -> None:
    """Show whether safe mode is active (master §1534-1550).

    Safe mode is a settings flag, not a toggle this command flips: set
    `ACR_SAFE_MODE=1` (or add it to `.env`) to enable it, then re-run.
    """
    settings = get_settings()
    state = "ON" if settings.safe_mode else "OFF"
    typer.echo(f"safe mode: {state}  (set ACR_SAFE_MODE=1 to enable)")
    if not settings.safe_mode:
        typer.echo("permitted when ON: inspection, retrieval, read-only model use, diagnostics")
        typer.echo("blocked when ON: skill activation, reversible-write/destructive tool calls")


@security_app.command("audit")
def security_audit(
    limit: int = typer.Option(20, "--limit", help="Maximum number of recent events to show."),
) -> None:
    """Show recent security audit events (permission checks, safe-mode blocks)."""
    settings = get_settings()

    async def _audit() -> list[TelemetryEvent]:
        async with session_scope(settings) as session:
            return await recent_audit_events(session, limit=limit)

    events = asyncio.run(_audit())
    if not events:
        typer.echo("no audit events recorded")
        return
    for event in events:
        action = event.payload.get("action", "?")
        outcome = event.payload.get("outcome", "?")
        typer.echo(f"{event.created_at.isoformat()}\t{action}\t{outcome}")


@security_app.command("scan")
def security_scan(
    text: str = typer.Argument(..., help="Text to scan for embedded-instruction patterns."),
) -> None:
    """Run the prompt-injection heuristic scanner over arbitrary text."""
    result = scan_for_injection(text)
    if not result.suspicious:
        typer.echo("clean: no known injection patterns matched")
        return
    typer.echo(f"suspicious: matched {', '.join(result.matched_patterns)}")


@learn_app.command("distill")
def learn_distill(
    task_id: str = typer.Argument(..., help="Id of a completed task to distill."),
) -> None:
    """Distill one task's raw trace into a memory candidate (master §631-644)."""
    settings = get_settings()

    async def _distill() -> tuple[DistillationResult, WriteEvaluation | None]:
        async with session_scope(settings) as session:
            result, evaluation = await distill_and_remember(session, task_id)
            await session.commit()
            return result, evaluation

    try:
        result, evaluation = asyncio.run(_distill())
    except TaskNotFoundError as exc:
        typer.echo(f"unknown task: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"{result.reason}: {result.raw_trace_bytes}B raw -> {result.distilled_bytes}B distilled "
        f"(ratio {result.compression_ratio:.1f}x)"
    )
    if evaluation is not None:
        typer.echo(f"write decision: {evaluation.decision.value} ({evaluation.reason})")


@learn_app.command("promote")
def learn_promote(
    min_utility: float = typer.Option(0.7, "--min-utility"),
    min_successful_uses: int = typer.Option(3, "--min-successful-uses"),
) -> None:
    """Promote sufficiently-useful candidate memories to confirmed (master §592-601)."""
    settings = get_settings()

    async def _promote() -> PromotionReport:
        async with session_scope(settings) as session:
            report = await promote_candidates(
                session, min_utility=min_utility, min_successful_uses=min_successful_uses
            )
            await session.commit()
            return report

    report = asyncio.run(_promote())
    typer.echo(f"promoted {len(report.promoted)} of {report.considered} candidates considered")
    for record in report.promoted:
        typer.echo(f"  {record.id}\t{record.subject}")


@learn_app.command("generate-skills")
def learn_generate_skills(
    min_repeats: int = typer.Option(DEFAULT_MIN_REPEATS, "--min-repeats"),
) -> None:
    """Generate quarantined candidate skills from repeated successful task objectives."""
    settings = get_settings()

    async def _generate() -> list[tuple[RepeatedPattern, SkillRecord]]:
        async with session_scope(settings) as session:
            patterns = await detect_repeated_successes(session, min_repeats=min_repeats)
            generated = [
                (pattern, await generate_candidate_skill(session, settings.data_dir, pattern))
                for pattern in patterns
            ]
            await session.commit()
            return generated

    generated = asyncio.run(_generate())
    if not generated:
        typer.echo("no repeated successful objectives found")
        return
    for pattern, record in generated:
        typer.echo(
            f"{record.id}\t{record.status.value}\t{pattern.occurrences}x\t{pattern.objective}"
        )


@learn_app.command("failures")
def learn_failures(
    objective: str = typer.Argument(
        ..., help="Objective/keywords to find similar past failures for."
    ),
    task_class: str | None = typer.Option(None, "--task-class"),
    limit: int = typer.Option(5, "--limit"),
) -> None:
    """Surface similar past FAILURE memories before attempting an objective (master §615-629)."""
    settings = get_settings()

    async def _find() -> list[SimilarFailure]:
        async with session_scope(settings) as session:
            return await find_similar_failures(
                session, objective=objective, task_class=task_class, limit=limit
            )

    results = asyncio.run(_find())
    if not results:
        typer.echo("no similar past failures recorded")
        return
    for f in results:
        typer.echo(f"[{f.task_class}] {f.symptom} (relevance={f.relevance:.2f})")
        if f.root_cause:
            typer.echo(f"  root cause: {f.root_cause}")
        if f.resolution:
            typer.echo(f"  resolution: {f.resolution}")


@learn_app.command("self-practice")
def learn_self_practice(
    limit: int | None = typer.Option(
        None, "--limit", help="Practice at most this many active skills. Default: all of them."
    ),
    min_quality_tier: int | None = typer.Option(
        None,
        "--min-quality-tier",
        help="Same meaning as `acr run`'s -- 0 (default) is always the zero-config mock "
        "provider, no cost.",
    ),
) -> None:
    """Grow real reliability/topology evidence by running every active
    skill's own declared applicability as a genuine practice objective
    (see docs/ARCHITECTURE.md) -- no external users required. Wire this
    into your own scheduler (cron, Task Scheduler) for repeated practice;
    ACR does not install one for you."""
    settings = get_settings()
    router = build_default_router(settings)
    resolved_tier = (
        min_quality_tier if min_quality_tier is not None else settings.default_min_quality_tier
    )

    async def _practice() -> list[PracticeRun]:
        profile = await router.select(min_quality_tier=resolved_tier)
        async with session_scope(settings) as session:
            runs = await run_self_practice(session, profile.provider, limit=limit)
            await session.commit()
            return runs

    try:
        runs = asyncio.run(_practice())
    except NoProviderAvailableError as exc:
        typer.echo(f"no provider available: {exc}")
        raise typer.Exit(code=1) from exc

    if not runs:
        typer.echo("no active skills with a declared task_class + applicability to practice")
        return
    for run in runs:
        typer.echo(
            f"{run.skill_id}\t{run.task_class}\ttask={run.task.id}\t"
            f"status={run.task.status.value}\tpassed={run.review.passed}"
        )
    typer.echo(f"{len(runs)} practice run(s) completed")


@skills_app.command("validate")
def skills_validate(
    skill_id: str = typer.Argument(..., help="Skill id to validate."),
    check_tools: bool = typer.Option(
        False, "--check-tools", help="Check declared tools against the default tool registry."
    ),
) -> None:
    """Run the validation pipeline against a registered skill (master §717-731)."""
    settings = get_settings()

    async def _validate() -> ValidationReport:
        async with session_scope(settings) as session:
            record = await get(session, skill_id)
            if record is None:
                raise SkillNotFoundError(skill_id)
            tool_registry = build_default_registry() if check_tools else None
            report = await run_validation(
                session, record, tool_registry=tool_registry, telemetry=TelemetryRecorder()
            )
            await session.commit()
            return report

    try:
        report = asyncio.run(_validate())
    except SkillNotFoundError as exc:
        typer.echo(f"unknown skill: {exc}")
        raise typer.Exit(code=1) from exc

    for stage in report.stages:
        typer.echo(f"[{stage.status.value:8}] {stage.name}: {stage.detail}")
    typer.echo(f"overall: {'PASSED' if report.passed else 'FAILED'}")
    if not report.passed:
        raise typer.Exit(code=1)


@skills_app.command("evolve")
def skills_evolve(
    skill_id: str = typer.Argument(..., help="Baseline skill id to evolve."),
    description: str | None = typer.Option(
        None, "--description", help="Override description for the new candidate version."
    ),
) -> None:
    """Create a new candidate version of a skill without touching the original."""
    settings = get_settings()
    overrides: dict[str, object] = {}
    if description is not None:
        overrides["description"] = description

    async def _evolve() -> SkillRecord:
        async with session_scope(settings) as session:
            baseline = await get(session, skill_id)
            if baseline is None:
                raise SkillNotFoundError(skill_id)
            candidate = await create_candidate_version(
                session, settings.data_dir, baseline, overrides
            )
            await session.commit()
            return candidate

    try:
        candidate = asyncio.run(_evolve())
    except SkillNotFoundError as exc:
        typer.echo(f"unknown skill: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"{candidate.id} -> {candidate.status.value}")


@skills_app.command("compare-evolution")
def skills_compare_evolution(
    baseline_id: str = typer.Argument(...),
    candidate_id: str = typer.Argument(...),
) -> None:
    """Compare a baseline and candidate skill version."""
    settings = get_settings()

    async def _compare() -> EvolutionComparison:
        async with session_scope(settings) as session:
            baseline = await get(session, baseline_id)
            candidate = await get(session, candidate_id)
            if baseline is None:
                raise SkillNotFoundError(baseline_id)
            if candidate is None:
                raise SkillNotFoundError(candidate_id)
            return compare_versions(baseline, candidate)

    try:
        comparison = asyncio.run(_compare())
    except SkillNotFoundError as exc:
        typer.echo(f"unknown skill: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"reliability: {comparison.baseline_reliability:.2f} -> "
        f"{comparison.candidate_reliability:.2f}"
    )
    typer.echo(
        f"tokens: {comparison.baseline_token_estimate} -> {comparison.candidate_token_estimate}"
    )
    typer.echo(f"recommend_promote={comparison.recommend_promote}: {comparison.reason}")


@skills_app.command("promote-evolution")
def skills_promote_evolution(
    baseline_id: str = typer.Argument(...),
    candidate_id: str = typer.Argument(...),
) -> None:
    """Deprecate the baseline (if active) and activate the candidate version."""
    settings = get_settings()

    async def _promote() -> SkillRecord:
        async with session_scope(settings) as session:
            baseline = await get(session, baseline_id)
            if baseline is None:
                raise SkillNotFoundError(baseline_id)
            promoted = await promote_evolution(
                session, baseline, candidate_id, safe_mode=settings.safe_mode
            )
            await session.commit()
            return promoted

    try:
        promoted = asyncio.run(_promote())
    except SkillNotFoundError as exc:
        typer.echo(f"unknown skill: {exc}")
        raise typer.Exit(code=1) from exc
    except (SafeModeError, InvalidSkillTransition) as exc:
        typer.echo(f"denied: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"{promoted.id} -> {promoted.status.value}")


@skills_app.command("rollback-evolution")
def skills_rollback_evolution(
    active_id: str = typer.Argument(..., help="Currently active skill id to deprecate."),
    restore_id: str = typer.Argument(..., help="Prior version to reactivate."),
) -> None:
    """Deprecate the currently active version and restore a prior one."""
    settings = get_settings()

    async def _rollback() -> SkillRecord:
        async with session_scope(settings) as session:
            restored = await rollback_evolution(
                session, active_id=active_id, restore_id=restore_id, safe_mode=settings.safe_mode
            )
            await session.commit()
            return restored

    try:
        restored = asyncio.run(_rollback())
    except SkillNotFoundError as exc:
        typer.echo(f"unknown skill: {exc}")
        raise typer.Exit(code=1) from exc
    except (SafeModeError, InvalidSkillTransition) as exc:
        typer.echo(f"denied: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"restored {restored.id} -> {restored.status.value}")


@agents_app.command("plan")
def agents_plan(
    objective: str = typer.Argument(..., help="Objective to plan an agent for."),
    role: str = typer.Option("worker", "--role"),
    token_budget: int = typer.Option(4000, "--token-budget"),
    task_class: str | None = typer.Option(
        None, "--task-class", help="Improves routing precision; required by `agents spawn`."
    ),
) -> None:
    """Build an AgentSpec for an objective, scoped by real skill/tool routing."""
    settings = get_settings()

    async def _plan() -> tuple[AgentSpec, list[SimilarFailure]]:
        async with session_scope(settings) as session:
            spec = await plan_agent(
                session, objective, role=role, token_budget=token_budget, task_class=task_class
            )
            similar = await find_similar_failures(
                session, objective=objective, task_class=task_class, limit=3
            )
            return spec, similar

    spec, similar_failures = asyncio.run(_plan())
    estimate = estimate_spawn(spec)
    typer.echo(f"{spec.id}\trole={spec.role}\ttoken_budget={spec.token_budget}")
    typer.echo(f"skills={spec.skills or '-'}")
    typer.echo(f"tools={spec.tools or '-'}")
    typer.echo(
        f"estimate: quality_gain={estimate.expected_quality_gain:.2f} "
        f"overhead={estimate.coordination_overhead:.2f} "
        f"security_risk={estimate.security_risk:.2f} "
        f"worth_spawning={estimate.worth_spawning}"
    )
    if similar_failures:
        typer.echo(f"similar past failures: {len(similar_failures)} (see `acr learn failures`)")
        for f in similar_failures:
            typer.echo(f"  [{f.task_class}] {f.symptom}")


@agents_app.command("spawn")
def agents_spawn(
    objective: str = typer.Argument(..., help="Objective to plan and spawn an agent for."),
    task_class: str = typer.Option(
        ...,
        "--task-class",
        help="Task class this spawn belongs to -- routes skills more precisely and is "
        "how its outcome feeds back into skill reliability and topology recommendations "
        "(`acr agents topology <task-class>`). Required: ACR has no classifier to infer it.",
    ),
    role: str = typer.Option("worker", "--role"),
    force: bool = typer.Option(
        False, "--force", help="Spawn even if the spawn estimate recommends against it."
    ),
) -> None:
    """Plan an agent, then run it end to end via the task engine and review the result."""
    settings = get_settings()

    async def _spawn() -> tuple[
        AgentSpec, SpawnEstimate, list[SimilarFailure], tuple[Task, PanelResult] | None
    ]:
        async with session_scope(settings) as session:
            spec = await plan_agent(session, objective, role=role, task_class=task_class)
            estimate = estimate_spawn(spec)
            similar = await find_similar_failures(
                session, objective=objective, task_class=task_class, limit=3
            )
            try:
                result = await spawn_agent(
                    session,
                    spec,
                    MockProvider(),
                    TelemetryRecorder(),
                    task_class=task_class,
                    force=force,
                )
            except SpawnNotWorthwhileError:
                return spec, estimate, similar, None
            await session.commit()
            return spec, estimate, similar, result

    spec, estimate, similar_failures, result = asyncio.run(_spawn())
    if similar_failures:
        typer.echo(f"similar past failures: {len(similar_failures)} (see `acr learn failures`)")
        for f in similar_failures:
            typer.echo(f"  [{f.task_class}] {f.symptom}")
    if result is None:
        typer.echo(
            f"not spawned: estimate does not justify it "
            f"(quality_gain={estimate.expected_quality_gain:.2f}, "
            f"overhead+risk={estimate.coordination_overhead + estimate.security_risk:.2f}); "
            f"use --force to spawn anyway"
        )
        raise typer.Exit(code=1)

    task, review = result
    typer.echo(f"{spec.id}: task {task.id} -> {task.status.value}")
    typer.echo(f"review: passed={review.passed} agreement={review.agreement:.2f}")


@agents_app.command("topology")
def agents_topology(
    task_class: str = typer.Argument(..., help="Task class to look up topology history for."),
    min_samples: int = typer.Option(DEFAULT_TOPOLOGY_MIN_SAMPLES, "--min-samples"),
) -> None:
    """Recommend a worker count for a task class, if there's enough evidence."""
    settings = get_settings()

    async def _recommend() -> TopologyRecommendation | None:
        async with session_scope(settings) as session:
            return await recommend_topology(session, task_class, min_samples=min_samples)

    recommendation = asyncio.run(_recommend())
    if recommendation is None:
        typer.echo(f"no recommendation for {task_class!r}: insufficient evidence")
        return
    typer.echo(
        f"{task_class}: {recommendation.recommended_worker_count} worker(s) recommended "
        f"({recommendation.detail})"
    )


@dashboard_app.command("serve")
def dashboard_serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Serve the operational dashboard (master §1225-1240)."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(create_dashboard_app(settings), host=host, port=port)


@mcp_app.command("serve")
def mcp_serve(
    transport: str = typer.Option("stdio", "--transport", help="stdio, sse, or streamable-http."),
    host: str = typer.Option("127.0.0.1", "--host", help="Ignored for stdio."),
    port: int = typer.Option(8767, "--port", help="Ignored for stdio."),
) -> None:
    """Serve ACR's memory/skill search and task execution over MCP."""
    settings = get_settings()
    server = create_mcp_server(settings)
    kwargs = {} if transport == "stdio" else {"host": host, "port": port}
    server.run(transport=transport, **kwargs)  # type: ignore[arg-type]


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Apply all pending schema migrations.

    Unlike `uv run alembic upgrade head` (which needs the repo's
    alembic.ini and is the dev/source-checkout path), this works from a
    plain `pip install acr`/`uv tool install acr` too -- no alembic.ini
    required, since the migrations themselves ship inside the installed
    package (see acr.db.migrate).
    """
    settings = get_settings()
    settings.ensure_data_dir()
    upgrade_to_head()
    typer.echo(f"database upgraded to head: {settings.database_path}")


@backup_app.command("create")
def backup_create(
    output: Path | None = typer.Option(
        None, "--output", help="Archive path. Defaults to <data_dir>/backups/<timestamp>.zip."
    ),
) -> None:
    """Snapshot the local data directory (database + generated skills) into
    a single archive with a SHA-256 manifest. Does not include the
    first-party skills/ package tree -- that's already in git."""
    settings = get_settings()
    archive_path = output or (
        settings.data_dir / "backups" / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}.zip"
    )
    result = create_backup(settings.data_dir, archive_path)
    typer.echo(f"{result.archive_path}\t{result.file_count} file(s)\t{result.total_bytes} bytes")


@backup_app.command("restore")
def backup_restore(
    archive: Path = typer.Argument(..., help="Archive created by `acr backup create`."),
    target_dir: Path = typer.Option(
        ..., "--target-dir", help="Directory to restore into. Refused if non-empty unless --force."
    ),
    force: bool = typer.Option(
        False, "--force", help="Restore into a non-empty target directory anyway."
    ),
) -> None:
    """Verify every file's hash against the archive's own manifest before
    writing anything, then restore. Never overwrites a populated target
    directory unless --force is passed."""
    try:
        count = restore_backup(archive, target_dir, force=force)
    except RestoreTargetNotEmptyError as exc:
        typer.echo(f"target directory is not empty: {exc} (use --force to proceed anyway)")
        raise typer.Exit(code=1) from exc
    except BackupIntegrityError as exc:
        typer.echo(f"integrity check failed, nothing was written: {exc}")
        raise typer.Exit(code=1) from exc
    except UnsafeArchiveMemberError as exc:
        typer.echo(f"refused an unsafe archive member path, nothing was written: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"restored {count} file(s) to {target_dir}")


def _echo_proposal(p: Proposal) -> None:
    typer.echo(f"{p.id}  [{p.status.value}]  {p.kind.value}  subject={p.subject}")
    typer.echo(f"  {p.reason}")


@improve_app.command("propose-skill-evolution")
def improve_propose_skill_evolution(
    baseline_id: str = typer.Argument(..., help="Currently active skill id."),
    candidate_id: str = typer.Argument(..., help="Evolved candidate skill id to compare."),
) -> None:
    """Compare a skill evolution candidate against its baseline; propose promoting it
    only if the comparison actually recommends it (master §1721-1727)."""
    settings = get_settings()

    async def _propose() -> Proposal | None:
        async with session_scope(settings) as session:
            proposal = await propose_skill_evolution(
                session,
                settings,
                TelemetryRecorder(),
                baseline_id=baseline_id,
                candidate_id=candidate_id,
            )
            await session.commit()
            return proposal

    try:
        proposal = asyncio.run(_propose())
    except SelfImprovementDisabledError as exc:
        typer.echo(f"disabled: {exc}")
        raise typer.Exit(code=1) from exc
    except SkillNotFoundError as exc:
        typer.echo(f"unknown skill: {exc}")
        raise typer.Exit(code=1) from exc

    if proposal is None:
        typer.echo("no proposal: candidate does not improve on the baseline")
        return
    _echo_proposal(proposal)


@improve_app.command("propose-routing-optimization")
def improve_propose_routing_optimization(
    task_class: str = typer.Argument(..., help="Task class to compare model outcomes for."),
    current_model: str = typer.Argument(..., help="The model currently preferred/reachable first."),
    candidate_model: str = typer.Argument(..., help="The model to compare it against."),
    min_samples: int = typer.Option(
        DEFAULT_ROUTING_MIN_SAMPLES,
        "--min-samples",
        help="Minimum real recorded spawns per model to have an opinion.",
    ),
) -> None:
    """Compare real per-model outcomes for a task class (from `acr agents spawn`
    evidence) and propose switching only if the comparison clearly recommends
    it. Advisory only -- see docs/ARCHITECTURE.md: there is no safe mechanism
    to auto-apply a routing change, so this never auto-applies regardless of
    ACR_AUTO_APPLY_PROPOSALS, and approving it just marks it reviewed."""
    settings = get_settings()

    async def _propose() -> Proposal | str | None:
        async with session_scope(settings) as session:
            outcomes = await model_outcomes_for_task_class(
                session, task_class=task_class, min_samples=min_samples
            )
            by_name = {o.model_name: o for o in outcomes}
            missing = [m for m in (current_model, candidate_model) if m not in by_name]
            if missing:
                return (
                    f"insufficient evidence for {missing} in task_class={task_class!r} "
                    f"(need >= {min_samples} real recorded spawns each)"
                )
            proposal = await propose_routing_optimization(
                session,
                settings,
                TelemetryRecorder(),
                task_class=task_class,
                current=by_name[current_model],
                candidate=by_name[candidate_model],
            )
            await session.commit()
            return proposal

    try:
        result = asyncio.run(_propose())
    except SelfImprovementDisabledError as exc:
        typer.echo(f"disabled: {exc}")
        raise typer.Exit(code=1) from exc

    if isinstance(result, str):
        typer.echo(result)
        raise typer.Exit(code=1)
    if result is None:
        typer.echo(f"no proposal: {candidate_model} does not clearly outperform {current_model}")
        return
    _echo_proposal(result)


@improve_app.command("list")
def improve_list(
    status: ProposalStatus | None = typer.Option(None, "--status", help="Filter by status."),
) -> None:
    """List self-improvement proposals."""
    settings = get_settings()

    async def _list() -> list[Proposal]:
        async with session_scope(settings) as session:
            return await list_proposals(session, status=status)

    proposals = asyncio.run(_list())
    if not proposals:
        typer.echo("no proposals")
        return
    for p in proposals:
        _echo_proposal(p)


@improve_app.command("approve")
def improve_approve(proposal_id: str = typer.Argument(...)) -> None:
    """Approve a pending proposal — applies its underlying change for real."""
    settings = get_settings()

    async def _approve() -> Proposal:
        async with session_scope(settings) as session:
            proposal = await approve_proposal(
                session, TelemetryRecorder(), proposal_id, safe_mode=settings.safe_mode
            )
            await session.commit()
            return proposal

    try:
        proposal = asyncio.run(_approve())
    except ProposalNotFoundError as exc:
        typer.echo(f"unknown proposal: {exc}")
        raise typer.Exit(code=1) from exc
    except ProposalNotPendingError as exc:
        typer.echo(f"cannot approve: {exc}")
        raise typer.Exit(code=1) from exc
    except SafeModeError as exc:
        typer.echo(f"denied: {exc}")
        raise typer.Exit(code=1) from exc

    _echo_proposal(proposal)


@improve_app.command("reject")
def improve_reject(proposal_id: str = typer.Argument(...)) -> None:
    """Reject a pending proposal — no change is applied."""
    settings = get_settings()

    async def _reject() -> Proposal:
        async with session_scope(settings) as session:
            proposal = await reject_proposal(session, TelemetryRecorder(), proposal_id)
            await session.commit()
            return proposal

    try:
        proposal = asyncio.run(_reject())
    except ProposalNotFoundError as exc:
        typer.echo(f"unknown proposal: {exc}")
        raise typer.Exit(code=1) from exc
    except ProposalNotPendingError as exc:
        typer.echo(f"cannot reject: {exc}")
        raise typer.Exit(code=1) from exc

    _echo_proposal(proposal)


def _echo_gc_plan(plan: GCPlan) -> None:
    for action in plan.actions:
        typer.echo(
            f"{action.memory_id}\t{action.type.value}\t"
            f"{action.current_status.value} -> {action.target_status.value}\t{action.reason}"
        )
    typer.echo(f"{len(plan.actions)} eligible / {plan.considered} considered")


@memory_app.command("gc-plan")
def memory_gc_plan(
    superseded_retention_days: int = typer.Option(
        DEFAULT_SUPERSEDED_RETENTION_DAYS, "--superseded-retention-days"
    ),
    quarantined_retention_days: int = typer.Option(
        DEFAULT_QUARANTINED_RETENTION_DAYS, "--quarantined-retention-days"
    ),
    stale_candidate_days: int = typer.Option(
        DEFAULT_STALE_CANDIDATE_DAYS, "--stale-candidate-days"
    ),
) -> None:
    """Dry run: show which memory records `memory gc-apply` would archive."""
    settings = get_settings()

    async def _plan() -> GCPlan:
        async with session_scope(settings) as session:
            return await plan_gc(
                session,
                superseded_retention_days=superseded_retention_days,
                quarantined_retention_days=quarantined_retention_days,
                stale_candidate_days=stale_candidate_days,
            )

    plan = asyncio.run(_plan())
    if not plan.actions:
        typer.echo(f"no records eligible for archival ({plan.considered} considered)")
        return
    _echo_gc_plan(plan)
    typer.echo("run `acr memory gc-apply` to apply")


@memory_app.command("gc-apply")
def memory_gc_apply(
    superseded_retention_days: int = typer.Option(
        DEFAULT_SUPERSEDED_RETENTION_DAYS, "--superseded-retention-days"
    ),
    quarantined_retention_days: int = typer.Option(
        DEFAULT_QUARANTINED_RETENTION_DAYS, "--quarantined-retention-days"
    ),
    stale_candidate_days: int = typer.Option(
        DEFAULT_STALE_CANDIDATE_DAYS, "--stale-candidate-days"
    ),
) -> None:
    """Recompute the GC plan and apply it -- archives every eligible record.
    CONFIRMED records are never eligible at any age; see `acr memory gc-plan`
    to review first."""
    settings = get_settings()

    async def _apply() -> tuple[GCPlan, int]:
        async with session_scope(settings) as session:
            plan = await plan_gc(
                session,
                superseded_retention_days=superseded_retention_days,
                quarantined_retention_days=quarantined_retention_days,
                stale_candidate_days=stale_candidate_days,
            )
            applied = await apply_gc_plan(session, plan)
            await session.commit()
            return plan, applied

    plan, applied = asyncio.run(_apply())
    if not plan.actions:
        typer.echo(f"no records eligible for archival ({plan.considered} considered)")
        return
    _echo_gc_plan(plan)
    typer.echo(f"archived {applied}/{len(plan.actions)} record(s)")


@memory_app.command("calibration")
def memory_calibration(
    min_uses: int = typer.Option(
        DEFAULT_MIN_USES,
        "--min-uses",
        help="Minimum real recorded uses (successful+failed) to include a record.",
    ),
) -> None:
    """Does stored memory confidence actually predict outcomes? A fixed-bin
    reliability curve + Brier score over real successful_uses/failed_uses
    evidence -- a record with no recorded uses has no empirical outcome to
    compare against and is excluded, not scored as 0%."""
    settings = get_settings()

    async def _compute() -> CalibrationReport:
        async with session_scope(settings) as session:
            return await compute_calibration(session, min_uses=min_uses)

    report = asyncio.run(_compute())
    if not report.bins:
        typer.echo(
            f"no evidenced records to calibrate against "
            f"({report.records_excluded_no_evidence} excluded, 0 with >= {min_uses} use(s))"
        )
        return
    for b in report.bins:
        typer.echo(
            f"[{b.lower:.1f}, {b.upper:.1f})\tn={b.count}\t"
            f"mean_confidence={b.mean_confidence:.2f}\t"
            f"empirical_success_rate={b.empirical_success_rate:.2f}"
        )
    typer.echo(
        f"brier_score={report.brier_score:.4f} (0=perfectly calibrated, lower is better)\t"
        f"{report.records_considered} record(s) considered, "
        f"{report.records_excluded_no_evidence} excluded (no recorded uses)"
    )


@memory_app.command("record-commit")
def memory_record_commit(
    rev: str = typer.Argument(
        "HEAD", help="Git revision to record (default: HEAD, i.e. the most recent commit)."
    ),
) -> None:
    """Turn a real git commit's own message into a DECISION memory --
    zero manual step, the actual mechanism `.githooks/post-commit` calls
    automatically after every commit to this repo. Re-running for a
    commit that's already been recorded is a real no-op (subject is keyed
    on the commit's own sha), not a duplicate entry."""
    settings = get_settings()

    async def _record() -> tuple[WriteEvaluation, MemoryRecord | None]:
        async with session_scope(settings) as session:
            evaluation, record = await record_commit_as_decision(session, rev)
            await session.commit()
            return evaluation, record

    try:
        evaluation, _ = asyncio.run(_record())
    except GitCommandError as exc:
        typer.echo(f"git error: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"{evaluation.decision.value}: {evaluation.reason}")


if __name__ == "__main__":
    app()
