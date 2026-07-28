"""Memory-recall benchmark suite (master §1063: "memory recall" category).

Seeds real facts through `acr.memory.write_controller.remember` and checks
whether `retrieve()` actually surfaces the right one for a query that should
match it — genuine execution against Phase 2 code, not a scripted result.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from acr.benchmarks.models import BenchmarkCase
from acr.memory import MemoryCandidate, MemoryScope, MemoryType
from acr.memory.retrieval import retrieve
from acr.memory.write_controller import remember

SUITE_NAME = "memory-recall"

# (subject, content, query that should retrieve `content`)
_FIXTURES: list[tuple[str, str, str]] = [
    ("acr.storage", "ACR persists data in a local SQLite file.", "Where does ACR store data?"),
    ("acr.cli", "ACR's CLI is built with Typer.", "What CLI framework does ACR use?"),
    (
        "acr.tests",
        "ACR tests run with pytest and pytest-asyncio.",
        "How are ACR's tests run?",
    ),
]


async def seed(session: AsyncSession) -> None:
    for subject, content, _ in _FIXTURES:
        await remember(
            session,
            MemoryCandidate(
                type=MemoryType.SEMANTIC,
                scope=MemoryScope.PROJECT,
                subject=subject,
                content=content,
                source_type="benchmark",
                confidence=0.9,
                evidence="benchmark fixture",
            ),
        )


def build_cases(session: AsyncSession) -> list[BenchmarkCase]:
    """Call `seed(session)` before running these cases."""
    cases: list[BenchmarkCase] = []
    for subject, content, query in _FIXTURES:

        async def run(query: str = query, content: str = content) -> bool:
            results = await retrieve(session, query=query)
            return any(r.record.content == content for r in results)

        cases.append(
            BenchmarkCase(
                id=f"recall::{subject}",
                category=SUITE_NAME,
                description=f"retrieve() surfaces the fact matching: {query!r}",
                run=run,
                expected=True,
            )
        )
    return cases
