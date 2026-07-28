"""ACR command-line interface (master spec §61).

`doctor`, `version`, `run`, and `context compile` are implemented so far; the
remaining subcommands (`task`, `status`, `memory`, `skills`, ...) land with
the phases that give them something real to do.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from acr import __version__
from acr.agents.critic import review_agent_task
from acr.agents.factory import estimate_spawn, spawn_agent
from acr.agents.models import AgentSpec, SpawnEstimate
from acr.agents.planner import plan_agent
from acr.agents.topology import TopologyRecommendation, recommend_topology
from acr.benchmarks import memory_recall
from acr.benchmarks.models import BenchmarkRun
from acr.benchmarks.runner import run_suite
from acr.config import get_settings
from acr.context.compiler import compile_context
from acr.context.models import ContextBundle
from acr.core.execution import run_task
from acr.core.tasks.models import Task, TaskStatus
from acr.db.base import session_scope
from acr.doctor import CheckStatus, run_checks
from acr.evaluation.evaluators import ExactMatchEvaluator
from acr.evaluation.regression import RegressionReport, detect_regression
from acr.evaluation.waste_analyzer import (
    DuplicateGroup,
    UtilizationReport,
    analyze_context_utilization,
    find_duplicate_memories,
)
from acr.learning.distillation import DistillationResult, TaskNotFoundError, distill_and_remember
from acr.learning.promotion import PromotionReport, promote_candidates
from acr.learning.skill_generation import (
    RepeatedPattern,
    detect_repeated_successes,
    generate_candidate_skill,
)
from acr.logging import configure_logging, get_logger
from acr.memory.write_controller import WriteEvaluation
from acr.providers.base import CompletionRequest
from acr.providers.mock import MockProvider
from acr.routing.models import ModelProfile, RoutedCompletion, build_default_router
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
from acr.telemetry.models import TelemetryEvent
from acr.telemetry.recorder import TelemetryRecorder
from acr.tools.default_tools import build_default_registry
from acr.tools.exposure import expose_tools
from acr.tools.invocation import invoke_tool
from acr.tools.models import ToolSpec
from acr.tools.registry import ToolNotFoundError

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
app.add_typer(context_app)
app.add_typer(skills_app)
app.add_typer(benchmark_app)
app.add_typer(waste_app)
app.add_typer(learn_app)
app.add_typer(models_app)
app.add_typer(tools_app)
app.add_typer(security_app)
app.add_typer(agents_app)

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
def run(
    objective: str = typer.Argument(..., help="Objective for the task engine to execute."),
) -> None:
    """Create and execute a task end to end (task engine + provider + telemetry).

    Uses the local, zero-config `mock` provider. Real provider routing
    (Ollama, cloud, escalation) is master spec Phase 6.
    """
    logger = get_logger("acr.cli.run")
    settings = get_settings()

    async def _run() -> Task:
        async with session_scope(settings) as session:
            return await run_task(session, objective, MockProvider(), TelemetryRecorder())

    task = asyncio.run(_run())
    typer.echo(f"task {task.id} -> {task.status.value}")
    logger.info("cli.run.completed", task_id=task.id, status=task.status.value)

    if task.status is TaskStatus.FAILED:
        raise typer.Exit(code=1)


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

    routed = asyncio.run(_route())
    typer.echo(f"tried={','.join(routed.tried_profiles)} escalated={routed.escalated}")
    typer.echo(routed.result.text)


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
# read-only search tools. Both `memory_search` and `skill_search` only need
# these two capabilities (see their ToolSpec.permissions in default_tools.py).
_CLI_OPERATOR_GRANTS = PermissionSet(
    granted=frozenset({Capability.MEMORY_READ, Capability.SKILL_READ})
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
    min_repeats: int = typer.Option(3, "--min-repeats"),
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
) -> None:
    """Build an AgentSpec for an objective, scoped by real skill/tool routing."""
    settings = get_settings()

    async def _plan() -> AgentSpec:
        async with session_scope(settings) as session:
            return await plan_agent(session, objective, role=role, token_budget=token_budget)

    spec = asyncio.run(_plan())
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


@agents_app.command("spawn")
def agents_spawn(
    objective: str = typer.Argument(..., help="Objective to plan and spawn an agent for."),
    role: str = typer.Option("worker", "--role"),
    force: bool = typer.Option(
        False, "--force", help="Spawn even if the spawn estimate recommends against it."
    ),
) -> None:
    """Plan an agent, then run it end to end via the task engine and review the result."""
    settings = get_settings()

    async def _spawn() -> tuple[AgentSpec, SpawnEstimate, Task | None]:
        async with session_scope(settings) as session:
            spec = await plan_agent(session, objective, role=role)
            estimate = estimate_spawn(spec)
            if not estimate.worth_spawning and not force:
                return spec, estimate, None
            task = await spawn_agent(session, spec, MockProvider(), TelemetryRecorder())
            await session.commit()
            return spec, estimate, task

    spec, estimate, task = asyncio.run(_spawn())
    if task is None:
        typer.echo(
            f"not spawned: estimate does not justify it "
            f"(quality_gain={estimate.expected_quality_gain:.2f}, "
            f"overhead+risk={estimate.coordination_overhead + estimate.security_risk:.2f}); "
            f"use --force to spawn anyway"
        )
        raise typer.Exit(code=1)

    review = review_agent_task(task)
    typer.echo(f"{spec.id}: task {task.id} -> {task.status.value}")
    typer.echo(f"review: passed={review.passed} agreement={review.agreement:.2f}")


@agents_app.command("topology")
def agents_topology(
    task_class: str = typer.Argument(..., help="Task class to look up topology history for."),
    min_samples: int = typer.Option(3, "--min-samples"),
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


if __name__ == "__main__":
    app()
