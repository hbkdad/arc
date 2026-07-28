"""ACR command-line interface (master spec §61).

`doctor`, `version`, and `run` are implemented so far; the remaining
subcommands (`task`, `status`, `memory`, `skills`, ...) land with the phases
that give them something real to do.
"""

from __future__ import annotations

import asyncio

import typer

from acr import __version__
from acr.config import get_settings
from acr.core.execution import run_task
from acr.core.tasks.models import Task, TaskStatus
from acr.db.base import session_scope
from acr.doctor import CheckStatus, run_checks
from acr.logging import configure_logging, get_logger
from acr.providers.mock import MockProvider
from acr.telemetry.recorder import TelemetryRecorder

app = typer.Typer(name="acr", help="ACR — Adaptive Cognitive Runtime", no_args_is_help=True)

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


if __name__ == "__main__":
    app()
