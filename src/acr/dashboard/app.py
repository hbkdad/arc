"""ACR operational dashboard (master §1225-1240).

Server-rendered, read-only HTML views over subsystems that already exist —
active tasks, agent activity, memory, skills, tool execution, security
events, benchmarks, and system health. Plain tables, no charting library,
no JS framework: "the dashboard must remain useful without advanced
graphics" (§1240). Cinematic/3D visualization is a separate later phase
(§1242 onward), not this one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from acr.config import Settings, get_settings
from acr.dashboard import queries
from acr.db.base import make_engine, make_session_factory
from acr.doctor import run_checks
from acr.routing.models import ModelProfile, build_default_router
from acr.security.audit import recent_audit_events
from acr.skills.registry import list_skills
from acr.tools.default_tools import build_default_registry

TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the dashboard FastAPI app against `settings` (or the process default)."""
    settings = settings or get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    app = FastAPI(title="ACR Dashboard")

    async def get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    @app.get("/", response_class=HTMLResponse)
    async def overview(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> HTMLResponse:
        checks = await run_checks(settings)
        task_counts = await queries.task_status_counts(session)
        event_counts = await queries.event_type_counts(session)
        return templates.TemplateResponse(
            request,
            "overview.html",
            {
                "active": "overview",
                "checks": checks,
                "task_counts": task_counts,
                "event_counts": event_counts,
            },
        )

    @app.get("/tasks", response_class=HTMLResponse)
    async def tasks(request: Request, session: AsyncSession = Depends(get_session)) -> HTMLResponse:
        rows = await queries.recent_tasks(session)
        counts = await queries.task_status_counts(session)
        return templates.TemplateResponse(
            request, "tasks.html", {"active": "tasks", "tasks": rows, "counts": counts}
        )

    @app.get("/agents", response_class=HTMLResponse)
    async def agents(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> HTMLResponse:
        rows = await queries.recent_topology(session)
        return templates.TemplateResponse(
            request, "agents.html", {"active": "agents", "records": rows}
        )

    @app.get("/memory", response_class=HTMLResponse)
    async def memory(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> HTMLResponse:
        type_counts = await queries.memory_type_counts(session)
        status_counts = await queries.memory_status_counts(session)
        rows = await queries.recent_memories(session)
        return templates.TemplateResponse(
            request,
            "memory.html",
            {
                "active": "memory",
                "type_counts": type_counts,
                "status_counts": status_counts,
                "records": rows,
            },
        )

    @app.get("/skills", response_class=HTMLResponse)
    async def skills(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> HTMLResponse:
        rows = await list_skills(session)
        return templates.TemplateResponse(
            request, "skills.html", {"active": "skills", "skills": rows}
        )

    @app.get("/tools", response_class=HTMLResponse)
    async def tools(request: Request, session: AsyncSession = Depends(get_session)) -> HTMLResponse:
        registry = build_default_registry()
        invocations = [
            e
            for e in await queries.recent_events(session, limit=100)
            if e.event_type == "security.audit"
        ]
        invocations = [
            e for e in invocations if str(e.payload.get("action", "")).startswith("tool.invoke:")
        ]
        return templates.TemplateResponse(
            request,
            "tools.html",
            {
                "active": "tools",
                "tools": registry.list_tools(),
                "invocations": invocations[:20],
            },
        )

    @app.get("/security", response_class=HTMLResponse)
    async def security(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> HTMLResponse:
        rows = await recent_audit_events(session)
        return templates.TemplateResponse(
            request, "security.html", {"active": "security", "events": rows}
        )

    @app.get("/benchmarks", response_class=HTMLResponse)
    async def benchmarks(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> HTMLResponse:
        rows = await queries.recent_benchmark_runs(session)
        return templates.TemplateResponse(
            request, "benchmarks.html", {"active": "benchmarks", "runs": rows}
        )

    @app.get("/routing", response_class=HTMLResponse)
    async def routing(request: Request) -> HTMLResponse:
        router = build_default_router(settings)
        availability: list[tuple[ModelProfile, bool]] = [
            (profile, await profile.provider.is_available()) for profile in router.profiles
        ]
        return templates.TemplateResponse(
            request, "routing.html", {"active": "routing", "availability": availability}
        )

    @app.get("/events", response_class=HTMLResponse)
    async def events(
        request: Request,
        session: AsyncSession = Depends(get_session),
        event_type: str | None = None,
    ) -> HTMLResponse:
        rows = await queries.recent_events(session, event_type=event_type, limit=100)
        counts = await queries.event_type_counts(session)
        return templates.TemplateResponse(
            request,
            "events.html",
            {
                "active": "events",
                "events": rows,
                "counts": counts,
                "selected_type": event_type,
            },
        )

    return app
