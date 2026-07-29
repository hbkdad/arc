"""ACR operational dashboard (master §1225-1240) and visualization (§1242-1256).

Server-rendered, read-only HTML views over subsystems that already exist —
active tasks, agent activity, memory, skills, tool execution, security
events, benchmarks, and system health. Plain tables, no charting library,
no JS framework: "the dashboard must remain useful without advanced
graphics" (§1240).

`/visualization` + `/api/graph` are the master §1242-1256 "cinematic
visualization" milestone, scoped down to a hand-written Canvas2D scene
(see `docs/ARCHITECTURE.md`'s Phase 12 section for why: it's real,
telemetry-driven, and adds zero new dependencies — no Three.js download, no
CDN script, consistent with every other phase's "no separate frontend
build step" and ACR's local-first/offline-usable requirement).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from acr.config import Settings, get_settings
from acr.dashboard import queries
from acr.db.base import make_engine, make_session_factory
from acr.doctor import run_checks
from acr.learning.proposals import ProposalStatus, list_proposals
from acr.routing.models import ModelProfile, build_default_router
from acr.security.audit import recent_audit_events
from acr.skills.registry import list_skills
from acr.telemetry.usage import usage_by_provider
from acr.tools.default_tools import build_default_registry

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

# Every status/outcome vocabulary the dashboard displays (task lifecycle,
# doctor checks, memory/skill/proposal status, audit outcomes, tri-state
# availability), mapped to one shared visual language -- a page-specific
# `status-{{ value }}` string match (the old approach) silently rendered
# unstyled for any value the author hadn't happened to add a CSS rule for.
# Presentation-only mapping (a CSS class name, not a decision), same
# category as the `"%.2f" | format(...)` calls already in these templates
# -- not new business logic the dashboard's docstring forbids.
_PILL_CLASSES = {
    "ok": "pill-ok",
    "completed": "pill-ok",
    "confirmed": "pill-ok",
    "active": "pill-ok",
    "approved": "pill-ok",
    "auto_applied": "pill-ok",
    "granted": "pill-ok",
    "available": "pill-ok",
    "true": "pill-ok",
    "warn": "pill-warn",
    "candidate": "pill-warn",
    "pending": "pill-warn",
    "experimental": "pill-warn",
    "planning": "pill-info",
    "executing": "pill-info",
    "verifying": "pill-info",
    "fail": "pill-danger",
    "failed": "pill-danger",
    "rejected": "pill-danger",
    "denied": "pill-danger",
    "blocked": "pill-danger",
    "quarantined": "pill-danger",
    "unavailable": "pill-danger",
    "false": "pill-danger",
    "cancelled": "pill-neutral",
    "superseded": "pill-neutral",
    "archived": "pill-neutral",
    "deprecated": "pill-neutral",
    "retired": "pill-neutral",
    "deleted": "pill-neutral",
    "created": "pill-neutral",
}


def _pill_class(value: object) -> str:
    """Jinja filter: map a status-shaped value to a `pill-*` CSS class."""
    key = str(getattr(value, "value", value)).lower()
    return _PILL_CLASSES.get(key, "pill-neutral")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the dashboard FastAPI app against `settings` (or the process default)."""
    settings = settings or get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["pill_class"] = _pill_class

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        # Mirrors the CLI's session_scope(), which always disposes its
        # engine in a finally -- `acr dashboard serve` runs long enough
        # that this rarely matters in practice, but a test/embedding
        # context that creates many apps (or a graceful-shutdown path)
        # shouldn't leak connection-pool resources.
        await engine.dispose()

    app = FastAPI(title="ACR Dashboard", lifespan=_lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
        # recent_audit_events() filters to security.audit at the SQL level
        # before applying its own limit -- filtering event_type in Python
        # *after* an event-type-agnostic `recent_events(limit=100)` (the
        # previous approach here) let a burst of non-audit telemetry (task
        # lifecycle, context.attribution, ...) crowd real tool invocations
        # out of the window entirely.
        invocations = [
            e
            for e in await recent_audit_events(session, limit=100)
            if str(e.payload.get("action", "")).startswith("tool.invoke:")
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
    async def routing(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> HTMLResponse:
        router = build_default_router(settings)
        availability: list[tuple[ModelProfile, bool]] = [
            (profile, await profile.provider.is_available()) for profile in router.profiles
        ]
        usage = await usage_by_provider(session, router.profiles)
        return templates.TemplateResponse(
            request,
            "routing.html",
            {"active": "routing", "availability": availability, "usage": usage},
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

    @app.get("/proposals", response_class=HTMLResponse)
    async def proposals(
        request: Request,
        session: AsyncSession = Depends(get_session),
        status: ProposalStatus | None = None,
    ) -> HTMLResponse:
        # FastAPI/pydantic validate `status` against the enum itself and
        # return a clean 422 for a bad value -- matching `improve_list`'s
        # equivalent CLI option, rather than letting `ProposalStatus(status)`
        # raise an unhandled ValueError here.
        rows = await list_proposals(session, status=status)
        return templates.TemplateResponse(
            request,
            "proposals.html",
            {
                "active": "proposals",
                "proposals": rows,
                "selected_status": status,
                "self_improvement_enabled": settings.self_improvement_enabled,
                "auto_apply_proposals": settings.auto_apply_proposals,
            },
        )

    @app.get("/visualization", response_class=HTMLResponse)
    async def visualization(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "visualization.html", {"active": "visualization"}
        )

    @app.get("/api/graph")
    async def api_graph(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
        """Real telemetry for `/visualization` to draw — no synthetic/random data.

        Every list here is a direct, small projection of an existing
        `acr.dashboard.queries` read: memory node clusters (type + count),
        recent tasks (state pulses), recent agent spawns (topology), and the
        raw event feed (token/activity flow). The frontend polls this on an
        interval rather than the server pushing over a websocket — simplest
        thing that's still genuinely live, no new transport to maintain.
        """
        memory_counts = await queries.memory_type_counts(session)
        tasks = await queries.recent_tasks(session, limit=15)
        agent_records = await queries.recent_topology(session, limit=15)
        events = await queries.recent_events(session, limit=40)
        return {
            "memory_types": [
                {"type": type_, "count": count} for type_, count in memory_counts.items()
            ],
            "tasks": [
                {
                    "id": t.id,
                    "objective": t.objective,
                    "status": t.status.value,
                    "updated_at": t.updated_at.isoformat(),
                }
                for t in tasks
            ],
            "agents": [
                {
                    "task_class": a.task_class,
                    "worker_count": a.worker_count,
                    "quality_score": a.quality_score,
                    "succeeded": a.succeeded,
                    "created_at": a.created_at.isoformat(),
                }
                for a in agent_records
            ],
            "events": [
                {
                    "event_type": e.event_type,
                    "task_id": e.task_id,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ],
        }

    return app
