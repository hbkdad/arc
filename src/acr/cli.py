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
from acr.config import get_settings
from acr.context.compiler import compile_context
from acr.context.models import ContextBundle
from acr.core.execution import run_task
from acr.core.tasks.models import Task, TaskStatus
from acr.db.base import session_scope
from acr.doctor import CheckStatus, run_checks
from acr.logging import configure_logging, get_logger
from acr.providers.mock import MockProvider
from acr.skills.models import SkillRecord, SkillStatus
from acr.skills.registry import list_skills, register, set_status
from acr.skills.routing import RoutedSkill, route
from acr.skills.search import SkillSearchResult, search
from acr.telemetry.recorder import TelemetryRecorder

app = typer.Typer(name="acr", help="ACR — Adaptive Cognitive Runtime", no_args_is_help=True)
context_app = typer.Typer(name="context", help="Context compiler operations.")
skills_app = typer.Typer(name="skills", help="Skill registry operations.")
app.add_typer(context_app)
app.add_typer(skills_app)

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


if __name__ == "__main__":
    app()
