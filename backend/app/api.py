from __future__ import annotations

import asyncio
import threading
import time

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from . import scoring, service
from .adapters import check_gateway_health
from .catalog import AGENTS, CATALOGUE_VERSION, FS_READ, FS_WRITE, slug
from .orchestrator import now_iso
from .sandbox import docker_available
from .schemas import AgentCreate, RunCreate

router = APIRouter(prefix="/api/v1")
TERMINAL = {"completed", "failed", "cancelled"}


def _s(request: Request):
    return request.app.state


# --------------------------------------------------------------------------- #
# Gateway status cache
#
# /health must answer fast even when the Bifrost gateway is down, so the
# gateway probe (which can take seconds to time out) is cached and refreshed
# out of band. /gateway/status always performs a fresh, bounded probe.
# --------------------------------------------------------------------------- #

_gateway_cache: dict = {}
_gateway_cache_at: float = 0.0
_gateway_lock = threading.Lock()
_gateway_refreshing = False


def _gateway_cached(settings, *, ttl: float, timeout: float) -> dict:
    """Return the cached gateway status, refreshing in the background when stale."""
    global _gateway_cache, _gateway_cache_at, _gateway_refreshing

    now = time.monotonic()
    with _gateway_lock:
        have = bool(_gateway_cache)
        fresh = have and (now - _gateway_cache_at) < ttl
        value = dict(_gateway_cache) if have else None
        start = have and not fresh and not _gateway_refreshing
        if start:
            _gateway_refreshing = True

    if start:
        def _refresh() -> None:
            global _gateway_cache, _gateway_cache_at, _gateway_refreshing
            try:
                probed = check_gateway_health(settings, timeout_sec=timeout)
            except Exception:  # noqa: BLE001 - a probe failure must never kill the thread
                probed = None
            finally:
                with _gateway_lock:
                    _gateway_refreshing = False
            if probed is not None:
                with _gateway_lock:
                    _gateway_cache = probed
                    _gateway_cache_at = time.monotonic()

        threading.Thread(target=_refresh, name="bifrost-gateway-probe", daemon=True).start()

    if fresh and value is not None:
        return {**value, "cached": True}

    if value is not None:
        # Stale but present: return it immediately, the refresh lands next time.
        return {**value, "cached": True, "stale": True}

    # Never probed: do one short synchronous probe so the first answer is useful.
    probed = check_gateway_health(settings, timeout_sec=min(timeout, 2.0))
    with _gateway_lock:
        _gateway_cache = probed
        _gateway_cache_at = time.monotonic()
    return {**probed, "cached": False}


@router.get("/health")
def health(request: Request):
    """Liveness + non-secret runtime configuration (never includes API keys).

    This endpoint must stay fast: the gateway is probed out of band and the
    last known result is returned, so a dead Bifrost gateway can never make
    Bifrost itself look offline.
    """
    st = _s(request)
    s = st.settings
    gw = _gateway_cached(
        s,
        ttl=float(getattr(s, "gateway_cache_ttl_sec", 15.0)),
        timeout=float(getattr(s, "gateway_probe_timeout_sec", 4.0)),
    )
    return {
        "status": "ok",
        "mode": s.mode,
        "providers": {
            "google_ai": bool(s.gemini_api_key),
            "openrouter": bool(s.openrouter_api_key),
        },
        "bifrost": {
            "enabled": gw["enabled"],
            "gateway_url": gw["gateway_url"],
            "reachable": gw["reachable"],
            "authenticated": gw.get("authenticated", False),
            "model_call_path_ok": gw.get("model_call_path_ok", False),
            "status": gw["status"],
            "error": gw.get("error"),
            "latency_ms": gw.get("latency_ms"),
            "cached": gw.get("cached", False),
        },
        "docker_available": docker_available(),
        "require_docker": bool(getattr(s, "require_docker", True)),
        "allow_host_sandbox": bool(getattr(s, "allow_host_sandbox", False)),
        "scorer_version": "scorer-2026.03.1",
        "catalogue_version": CATALOGUE_VERSION,
        "task_count": st.store.count_tasks(),
        "benchmark_count": st.store.count_benchmarks(),
    }


@router.get("/gateway/status")
def gateway_status(request: Request):
    """Maxim AI Bifrost gateway connection status for the Settings UI.

    Always performs a fresh, time-bounded probe against the configured
    gateway. Never returns API keys. Distinguishes "cannot reach the gateway"
    from "gateway reachable but authentication rejected".
    """
    s = _s(request).settings
    status = check_gateway_health(
        s, timeout_sec=float(getattr(s, "gateway_probe_timeout_sec", 4.0))
    )
    global _gateway_cache, _gateway_cache_at
    with _gateway_lock:
        _gateway_cache = status
        _gateway_cache_at = time.monotonic()
    return status


@router.get("/benchmarks")
def list_benchmarks(request: Request):
    """Return benchmarks with task_count taken from the live DB catalogue."""
    store = _s(request).store
    benches = store.list_benchmarks()
    # Recompute task_count from actual rows so stale hardcoded values cannot leak.
    for b in benches:
        b["task_count"] = store.count_tasks(b["id"])
    return benches


@router.get("/benchmarks/{benchmark_id}")
def get_benchmark(benchmark_id: str, request: Request):
    store = _s(request).store
    b = store.get_benchmark(benchmark_id)
    if b is None:
        raise HTTPException(404, f"benchmark '{benchmark_id}' not found")
    b = dict(b)
    b["task_count"] = store.count_tasks(benchmark_id)
    return b


@router.get("/benchmarks/{benchmark_id}/tasks")
def benchmark_tasks(
    benchmark_id: str,
    request: Request,
    search: str | None = Query(None, description="Filter by title, id, category or tag"),
    difficulty: str | None = Query(None, description="easy|medium|hard|expert"),
    category: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Tasks for one benchmark. Returns a plain list (frontend contract).
    Optional search/difficulty/category/limit/offset filter the list in-place.
    """
    st = _s(request).store
    if st.get_benchmark(benchmark_id) is None:
        raise HTTPException(404, f"benchmark '{benchmark_id}' not found")
    if difficulty is not None and difficulty.lower() not in ("easy", "medium", "hard", "expert"):
        raise HTTPException(422, f"invalid difficulty '{difficulty}' (use easy|medium|hard|expert)")
    return st.list_tasks(
        benchmark_id,
        search=search,
        difficulty=difficulty,
        category=category,
        limit=limit,
        offset=offset,
    )


@router.get("/tasks")
def all_tasks(
    request: Request,
    benchmark_id: str | None = Query(None),
    search: str | None = Query(None),
    difficulty: str | None = Query(None),
    category: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List tasks across the catalogue. Plain list for frontend compatibility.
    Supports optional filters and pagination query params.
    """
    st = _s(request).store
    if benchmark_id is not None and st.get_benchmark(benchmark_id) is None:
        raise HTTPException(404, f"benchmark '{benchmark_id}' not found")
    if difficulty is not None and difficulty.lower() not in ("easy", "medium", "hard", "expert"):
        raise HTTPException(422, f"invalid difficulty '{difficulty}' (use easy|medium|hard|expert)")
    return st.list_tasks(
        benchmark_id,
        search=search,
        difficulty=difficulty,
        category=category,
        limit=limit,
        offset=offset,
    )


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request):
    """Retrieve a single task by ID. Never returns hidden tests."""
    st = _s(request).store
    task = st.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"task '{task_id}' not found")
    return task


@router.get("/catalogue/integrity")
def catalogue_integrity_endpoint(request: Request):
    """Dataset / catalogue version and integrity information."""
    from .catalog import CATALOGUE_VERSION, build_catalogue, catalogue_integrity
    store = _s(request).store
    static = catalogue_integrity()
    db_task_ids = {t["id"] for t in store.list_tasks()}
    _, tasks = build_catalogue()
    expected_task_ids = {t["id"] for t, _ in tasks}
    missing_in_db = sorted(expected_task_ids - db_task_ids)
    extra_in_db = sorted(db_task_ids - expected_task_ids)
    return {
        **static,
        "db_benchmark_count": store.count_benchmarks(),
        "db_task_count": store.count_tasks(),
        "db_agent_count": len(store.list_agents()),
        "missing_tasks_in_db": missing_in_db,
        "extra_tasks_in_db": extra_in_db,
        "db_matches_catalogue": len(missing_in_db) == 0 and len(extra_in_db) == 0,
        "catalogue_version": CATALOGUE_VERSION,
    }


@router.get("/agents")
def list_agents(request: Request):
    return _s(request).store.list_agents()


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, request: Request):
    """Retrieve one agent by ID. Unknown IDs return 404 — never substituted."""
    a = _s(request).store.get_agent(agent_id)
    if a is None:
        raise HTTPException(404, f"agent '{agent_id}' not found")
    return a


@router.post("/agents")
def register_agent(body: AgentCreate, request: Request):
    store = _s(request).store
    existing = store.list_agents()
    base = slug(body.name) or "agent"
    aid, n = base, 2
    taken = {a["id"] for a in existing}
    while aid in taken:
        aid, n = f"{base}-{n}", n + 1
    used = {a["color_index"] for a in existing}
    color = body.color_index if body.color_index is not None else next((i for i in range(5) if i not in used), len(existing) % 5)
    tools = [t.model_dump() for t in body.tools] if body.tools else [FS_READ, FS_WRITE]
    doc = {"id": aid, "name": body.name.strip(), "model": body.model, "model_provider": body.model_provider,
           "description": body.description, "system_prompt_version": body.system_prompt_version, "tools": tools,
           "orchestration": body.orchestration, "memory": body.memory, "color_index": color, "enabled": True,
           "cost_per_1k_input": body.cost_per_1k_input, "cost_per_1k_output": body.cost_per_1k_output,
           "registered_at": now_iso()}
    store.put_agent(doc)
    return doc


@router.get("/runs")
def list_runs(request: Request, benchmark_id: str | None = None, status: str | None = None,
              limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    return _s(request).store.list_runs(benchmark_id, status, limit, offset)


@router.post("/runs", status_code=201)
def create_run(body: RunCreate, request: Request):
    st = _s(request)
    run = service.create_run(st.store, st.settings, body)   # snapshot: status is "queued" per the contract
    mode = st.store.get_run_mode(run["id"])
    st.orchestrator.submit(run["id"])                       # the worker may flip it to "running" immediately
    return run | {"execution_mode": mode}


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request):
    st = _s(request).store
    run = st.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"run '{run_id}' not found")
    return run | {"execution_mode": st.get_run_mode(run_id)}


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, request: Request):
    st = _s(request)
    run = st.store.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"run '{run_id}' not found")
    if run["status"] in TERMINAL:
        raise HTTPException(409, f"run is already {run['status']}")
    if run["status"] == "queued":
        run.update(status="cancelled", finished_at=now_iso())
        st.store.update_run(run)
    st.orchestrator.cancel(run_id)
    return st.store.get_run(run_id)


@router.get("/leaderboard")
def leaderboard(request: Request, benchmark_id: str | None = None):
    return scoring.build_leaderboard(_s(request).store.list_runs(benchmark_id=benchmark_id, limit=500))


@router.get("/dashboard")
def dashboard(request: Request):
    store = _s(request).store
    runs = store.list_runs(limit=500)
    calls = store.list_model_calls_for_runs([r["id"] for r in runs])
    return scoring.build_dashboard(runs, store.list_benchmarks(), model_calls=calls)




@router.get("/analytics")
def analytics(
    request: Request,
    benchmark_id: str | None = None,
    agent_id: str | None = None,
    provider: str | None = None,
):
    """Failure analytics + agent comparison from stored runs (not mock data)."""
    from . import analytics as analytics_mod
    store = _s(request).store
    runs = store.list_runs(benchmark_id=benchmark_id, limit=500)
    calls = store.list_model_calls_for_runs([r["id"] for r in runs])
    return analytics_mod.build_analytics(
        runs, benchmark_id=benchmark_id, agent_id=agent_id, provider=provider,
        model_calls=calls,
    )


@router.get("/analytics/comparison")
def analytics_comparison(request: Request, benchmark_id: str | None = None):
    from . import analytics as analytics_mod
    runs = _s(request).store.list_runs(benchmark_id=benchmark_id, limit=500)
    return analytics_mod.agent_comparison(runs, benchmark_id=benchmark_id)


@router.get("/analytics/failures")
def analytics_failures(
    request: Request,
    benchmark_id: str | None = None,
    agent_id: str | None = None,
    category: str | None = None,
):
    from . import analytics as analytics_mod
    runs = _s(request).store.list_runs(benchmark_id=benchmark_id, limit=500)
    failures = analytics_mod.extract_failures(runs)
    if agent_id:
        failures = [f for f in failures if f.get("agent_id") == agent_id]
    if category:
        failures = [f for f in failures if f.get("category") == category]
    return {"failures": failures, "count": len(failures)}


@router.get("/runs/{run_id}/report")
def run_report(run_id: str, request: Request):
    from . import analytics as analytics_mod
    run = _s(request).store.get_run(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    calls = _s(request).store.list_model_calls(run_id, limit=1000)
    return analytics_mod.build_benchmark_report(run, model_calls=calls)



@router.get("/runs/{run_id}/model-calls")
def list_model_calls(
    run_id: str,
    request: Request,
    agent_id: str | None = None,
    errors_only: bool = False,
    offset: int = 0,
    limit: int = 200,
):
    """Paginated model-call traces for a benchmark run (chronological)."""
    store = _s(request).store
    if store.get_run(run_id) is None:
        raise HTTPException(404, "Run not found")
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    calls = store.list_model_calls(
        run_id, agent_id=agent_id, errors_only=errors_only, offset=offset, limit=limit
    )
    return {
        "run_id": run_id,
        "calls": calls,
        "count": len(calls),
        "offset": offset,
        "limit": limit,
    }


@router.get("/runs/{run_id}/model-calls/summary")
def model_calls_summary(run_id: str, request: Request):
    store = _s(request).store
    if store.get_run(run_id) is None:
        raise HTTPException(404, "Run not found")
    return store.model_call_summary(run_id)


@router.get("/model-calls/{call_id}")
def get_model_call(call_id: str, request: Request):
    store = _s(request).store
    doc = store.get_model_call(call_id)
    if doc is None:
        raise HTTPException(404, "Model call not found")
    # Never surface credentials — metadata is already sanitized at write time
    return doc


@router.get("/runs/{run_id}/events")
def list_run_events(
    run_id: str, request: Request, after_id: int = 0, agent_id: str | None = None,
):
    """Return persisted orchestrator/agent events for a run in chronological order."""
    store = _s(request).store
    if store.get_run(run_id) is None:
        raise HTTPException(404, "Run not found")
    events = []
    for eid, ev in store.events_after(run_id, after_id):
        if agent_id and (ev.get("agent_id") not in (None, agent_id)):
            continue
        events.append(ev)
    return {"run_id": run_id, "events": events, "count": len(events)}


@router.get("/runs/{run_id}/tool-calls")
def list_tool_calls(run_id: str, request: Request, agent_id: str | None = None):
    """Aggregate tool calls from task results (linked to agent/task)."""
    store = _s(request).store
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    out = []
    for ar in run.get("agent_results") or []:
        aid = ar.get("agent_id") or ar.get("id")
        if agent_id and aid != agent_id:
            continue
        for tr in ar.get("task_results") or []:
            for i, c in enumerate(tr.get("tool_calls") or []):
                out.append({
                    "run_id": run_id,
                    "agent_id": aid,
                    "task_id": tr.get("task_id"),
                    "seq": i,
                    "tool": c.get("tool"),
                    "outcome": c.get("outcome"),
                    "duration_ms": c.get("duration_ms"),
                    "args_summary": c.get("args_summary"),
                })
    return {"run_id": run_id, "tool_calls": out, "count": len(out)}


@router.get("/runs/{run_id}/timeline")
def run_timeline(
    run_id: str,
    request: Request,
    agent_id: str | None = None,
    limit: int = 500,
):
    """Merged chronological view: execution events + model calls (no secrets)."""
    store = _s(request).store
    if store.get_run(run_id) is None:
        raise HTTPException(404, "Run not found")
    items: list[dict] = []
    for eid, ev in store.events_after(run_id, 0):
        if agent_id and (ev.get("agent_id") not in (None, agent_id)):
            continue
        items.append({
            "kind": "event",
            "id": f"ev-{eid}",
            "ts": ev.get("ts") or ev.get("timestamp"),
            "agent_id": ev.get("agent_id"),
            "task_id": ev.get("task_id"),
            "type": ev.get("type"),
            "message": ev.get("message"),
            "status": ev.get("status"),
            "gateway_request_id": ev.get("gateway_request_id"),
            "duration_ms": ev.get("duration_ms"),
        })
    calls = store.list_model_calls(run_id, agent_id=agent_id, limit=min(limit, 1000))
    for c in calls:
        items.append({
            "kind": "model_call",
            "id": c.get("id"),
            "ts": c.get("started_at") or c.get("finished_at"),
            "agent_id": c.get("agent_id"),
            "task_id": c.get("task_id"),
            "type": "model_call",
            "message": f"{c.get('provider')}/{c.get('model')} {'ok' if c.get('success') else 'error'}",
            "status": "ok" if c.get("success") else "error",
            "gateway_request_id": c.get("gateway_request_id"),
            "latency_ms": c.get("latency_ms"),
            "tokens_input": c.get("tokens_input"),
            "tokens_output": c.get("tokens_output"),
            "cost_usd": c.get("cost_usd"),
            "http_status": c.get("http_status"),
            "error": c.get("error"),
        })
    items.sort(key=lambda x: (x.get("ts") or "", x.get("id") or ""))
    if len(items) > limit:
        items = items[:limit]
    return {"run_id": run_id, "items": items, "count": len(items)}


@router.websocket("/runs/{run_id}/stream")
async def stream(ws: WebSocket, run_id: str):
    store = ws.app.state.store
    if store.get_run(run_id) is None:
        await ws.close(code=4404)
        return
    await ws.accept()
    last = 0
    try:
        while True:
            for eid, ev in store.events_after(run_id, last):
                await ws.send_json(ev)
                last = eid
            run = store.get_run(run_id)
            if run["status"] in TERMINAL and not store.events_after(run_id, last):
                break
            await asyncio.sleep(0.4)
        await ws.close()
    except WebSocketDisconnect:
        pass
