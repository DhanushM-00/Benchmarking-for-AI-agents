from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .catalog import AGENTS, CATALOGUE_VERSION, build_catalogue
from .config import Settings
from .db import Store
from .orchestrator import Orchestrator

# Optional production static UI (frontend/dist). When present the backend serves
# the SPA on the same origin so the user only needs one browser port.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

# Built-in agent IDs — only these are upserted on startup. User-created agents
# are never modified or removed by catalogue sync.
BUILTIN_AGENT_IDS = {a["id"] for a in AGENTS}


def sync_catalogue(store: Store) -> dict:
    """Idempotent catalogue synchronization.

    Always upserts the current in-code benchmarks, tasks (with hidden tests) and
    built-in agents. Never deletes rows, never touches runs/events/model_calls,
    and never overwrites user-created agents (any agent whose id is not in the
    built-in set).

    Safe to call on every startup against both fresh and partially-populated
    older databases so newly added catalogue entries appear without data loss.
    """
    benchmarks, tasks = build_catalogue()
    for i, b in enumerate(benchmarks):
        store.put_benchmark(b, i)
    for i, (t, hidden) in enumerate(tasks):
        store.put_task(t, i, hidden)
    for a in AGENTS:
        store.put_agent(a)
    return {
        "catalogue_version": CATALOGUE_VERSION,
        "benchmarks_synced": len(benchmarks),
        "tasks_synced": len(tasks),
        "builtin_agents_synced": len(AGENTS),
        "db_benchmark_count": store.count_benchmarks(),
        "db_task_count": store.count_tasks(),
    }


def seed(store: Store) -> None:
    """Backward-compatible name used by lifespan. Performs full catalogue sync."""
    sync_catalogue(store)


def seed_demo_runs(store: Store, orch: Orchestrator) -> None:
    """Eight finished *simulated* runs so a fresh dashboard isn't empty. Clearly labelled [SIMULATED]."""
    from .schemas import FairnessConfig, RunCreate
    from . import service
    cfg = FairnessConfig(
        time_limit_per_task_sec=120, max_tokens_per_task=32000, repeats=3, isolation="docker",
        container_image="bifrost/sandbox:py3.11-slim", network_policy="none", randomize_task_order=True,
        random_seed=42, scorer_version="scorer-2026.03.1", temperature=0.2, blinded_evaluation=True,
        metric_weights={"task_success": 0.25, "correctness": 0.30, "efficiency": 0.15, "tool_usage": 0.15, "consistency": 0.15})
    saved, orch.settings.sim_delay_ms = orch.settings.sim_delay_ms, 0
    for i, (bench, agents) in enumerate([
            ("python-core", ["atlas-coder", "nova-coder", "forge-coder"]), ("swe-lite", ["atlas-coder", "forge-coder"]),
            ("debug-suite", ["atlas-coder", "nova-coder", "forge-coder"]), ("api-dev", ["nova-coder", "forge-coder"]),
            ("file-io-stats", ["atlas-coder", "nova-coder", "forge-coder"]), ("python-core", ["atlas-coder", "forge-coder"]),
            ("swe-lite", ["atlas-coder", "nova-coder", "forge-coder"]), ("debug-suite", ["atlas-coder", "forge-coder"])]):
        c = cfg.model_copy(update={"random_seed": 42 + i})
        old, store_mode = orch.settings.mode, orch.settings.mode
        orch.settings.mode = "simulated"
        run = service.create_run(store, orch.settings, RunCreate(benchmark_id=bench, agent_ids=agents, fairness=c,
                                                                  notes="Demo run"))
        orch.settings.mode = old
        orch.run_sync(run["id"])
    orch.settings.sim_delay_ms = saved


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    store = Store(settings.db_path)
    seed(store)
    store.fail_interrupted_runs()
    orch = Orchestrator(store, settings)
    app.state.store, app.state.orchestrator = store, orch
    if settings.seed_demo and not store.list_runs(limit=1):
        seed_demo_runs(store, orch)
    yield
    orch.pool.shutdown(wait=False, cancel_futures=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Bifrost API", version="1.0.0", lifespan=lifespan,
                  description="Backend for the Bifrost AI-agent benchmarking platform (docs/API.md).")
    app.state.settings = settings
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        # docs/API.md: errors are {"detail": "<string>"} — the UI shows `detail` verbatim.
        parts = []
        for e in exc.errors():
            loc = ".".join(str(x) for x in e["loc"] if x not in ("body", "query", "path"))
            parts.append(f"{loc}: {e['msg']}" if loc else e["msg"])
        return JSONResponse(status_code=422, content={"detail": "; ".join(parts)})

    # Integrated single-port mode: serve the built SPA from frontend/dist when present.
    # API stays under /api; SPA assets and client-side routes are served from the same origin.
    # WebSocket run events remain on the API routes (same host). Bifrost stays internal.
    if _FRONTEND_DIST.is_dir() and (_FRONTEND_DIST / "index.html").is_file():
        assets = _FRONTEND_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            # Never shadow API or health
            if full_path.startswith("api") or full_path in ("health", "docs", "openapi.json", "redoc"):
                return JSONResponse(status_code=404, content={"detail": "Not Found"})
            candidate = _FRONTEND_DIST / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(_FRONTEND_DIST / "index.html")

    return app


app = create_app()
