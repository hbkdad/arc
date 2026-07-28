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
from acr.logging import configure_logging, get_logger
from acr.providers.base import CompletionRequest
from acr.providers.mock import MockProvider
from acr.routing.models import ModelProfile, RoutedCompletion, build_default_router
from acr.skills.models import SkillRecord, SkillStatus
from acr.skills.registry import list_skills, register, set_status
from acr.skills.routing import RoutedSkill, route
from acr.skills.search import SkillSearchResult, search
from acr.telemetry.recorder import TelemetryRecorder
from acr.tools.default_tools import build_default_registry
from acr.tools.exposure import expose_tools
from acr.tools.models import ToolSpec

app = typer.Typer(name="acr", help="ACR — Adaptive Cognitive Runtime", no_args_is_help=True)
context_app = typer.Typer(name="context", help="Context compiler operations.")
skills_app = typer.Typer(name="skills", help="Skill registry operations.")
benchmark_app = typer.Typer(name="benchmark", help="Benchmark suites.")
waste_app = typer.Typer(name="waste", help="Token waste analysis.")
models_app = typer.Typer(name="models", help="Model routing.")
tools_app = typer.Typer(name="tools", help="Tool registry operations.")
app.add_typer(context_app)
app.add_typer(skills_app)
app.add_typer(benchmark_app)
app.add_typer(waste_app)
app.add_typer(models_app)
app.add_typer(tools_app)

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
            record = await set_status(session, skill_id, status)
            await session.commit()
            return record

    record = asyncio.run(_set_status())
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


if __name__ == "__main__":
    app()
