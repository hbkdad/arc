"""`acr doctor` health checks (master spec §61, §72)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from acr.config import Settings
from acr.db.base import make_engine
from acr.providers.mock import MockProvider
from acr.providers.ollama import OllamaProvider

MIN_PYTHON = (3, 12)


class CheckStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    detail: str


def check_python_version() -> CheckResult:
    version = sys.version.split()[0]
    if sys.version_info >= MIN_PYTHON:
        return CheckResult("python_version", CheckStatus.OK, f"Python {version}")
    return CheckResult(
        "python_version",
        CheckStatus.FAIL,
        f"Python {version} — ACR requires >={MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
    )


def check_data_dir(settings: Settings) -> CheckResult:
    try:
        path = settings.ensure_data_dir()
    except OSError as exc:
        return CheckResult(
            "data_dir", CheckStatus.FAIL, f"cannot create {settings.data_dir}: {exc}"
        )
    return CheckResult("data_dir", CheckStatus.OK, str(path))


async def check_database(engine: AsyncEngine) -> CheckResult:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        return CheckResult("database", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}")
    return CheckResult("database", CheckStatus.OK, "SELECT 1 succeeded")


async def check_mock_provider() -> CheckResult:
    available = await MockProvider().is_available()
    status = CheckStatus.OK if available else CheckStatus.FAIL
    return CheckResult("provider_mock", status, "zero-config default provider")


async def check_ollama_provider() -> CheckResult:
    available = await OllamaProvider().is_available()
    if available:
        return CheckResult("provider_ollama", CheckStatus.OK, "reachable at localhost:11434")
    return CheckResult(
        "provider_ollama", CheckStatus.WARN, "not reachable (optional — mock provider is used)"
    )


async def run_checks(settings: Settings) -> list[CheckResult]:
    """Run all doctor checks and return their results in a fixed, stable order."""
    results = [check_python_version(), check_data_dir(settings)]
    engine = make_engine(settings)
    try:
        results.append(await check_database(engine))
    finally:
        await engine.dispose()
    results.append(await check_mock_provider())
    results.append(await check_ollama_provider())
    return results
