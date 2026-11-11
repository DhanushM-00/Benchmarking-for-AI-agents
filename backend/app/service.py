"""Run creation: validation, mode selection, preview parity report."""
from __future__ import annotations

from fastapi import HTTPException

from . import fairness
from .sandbox import docker_available
from .adapters import SUPPORTED_PROVIDERS
from .config import Settings
from .db import Store
from .orchestrator import now_iso
from .schemas import RunCreate


def pick_mode(
    settings: Settings,
    agents: list[dict],
    gradable: int,
    *,
    isolation: str,
    verify_chat: bool = True,
) -> tuple[str, list[str]]:
    """Return (mode, reasons_if_not_live).

    * ``simulated`` settings → always simulated (reasons empty).
    * ``live`` settings → live or HTTP 422 (never silent fallback).
    * ``auto`` → live when possible, else simulated with explicit reasons.

    When Bifrost is enabled we verify gateway reachability/auth and (optionally)
    that a real /v1/chat/completions call succeeds for each distinct agent model.
    A green /v1/models list alone is not treated as proof that completions work.
    """
    from .adapters import check_gateway_health, probe_chat_completion, bifrost_model_id

    wants = settings.mode
    if wants == "simulated":
        return "simulated", ["BIFROST_MODE=simulated"]

    problems: list[str] = []
    bifrost_on = getattr(settings, "bifrost_enabled", True)

    for a in agents:
        prov = a["model_provider"].strip().lower()
        if prov not in SUPPORTED_PROVIDERS:
            problems.append(f"{a['name']}: provider '{a['model_provider']}' has no adapter")
        elif not bifrost_on and not settings.provider_key(a["model_provider"]):
            problems.append(f"{a['name']}: no API key configured for {a['model_provider']}")

    if bifrost_on and not (settings.bifrost_gateway_url or "").strip():
        problems.append("BIFROST_GATEWAY_URL is empty")

    if gradable == 0:
        problems.append("selected tasks have no hidden test suites — live grading is impossible")

    if isolation == "docker" and not docker_available():
        if settings.allow_host_sandbox:
            # Allowed, but caller must record subprocess downgrade explicitly.
            pass
        else:
            problems.append(
                "Docker is not available and BIFROST_ALLOW_HOST_SANDBOX is not set "
                "(required for live isolation='docker')"
            )

    # Live path requires a working gateway — never assume /v1/models success is enough.
    if bifrost_on and not problems:
        health = check_gateway_health(
            settings,
            timeout_sec=float(getattr(settings, "gateway_probe_timeout_sec", 4.0)),
        )
        if health.get("status") == "unreachable":
            problems.append(health.get("error") or "Bifrost gateway unreachable")
        elif health.get("status") == "auth_error":
            problems.append(health.get("error") or "Bifrost authentication failed")
        elif health.get("status") == "misconfigured":
            problems.append(health.get("error") or "Bifrost misconfigured")
        elif health.get("status") == "disabled":
            problems.append(health.get("error") or "Bifrost disabled")
        elif not health.get("reachable") or not health.get("authenticated"):
            problems.append(
                health.get("error")
                or f"Bifrost not ready (status={health.get('status')})"
            )
        elif verify_chat:
            # Distinct models only — one probe per unique Bifrost model id.
            seen: set[str] = set()
            for a in agents:
                try:
                    mid = bifrost_model_id(a)
                except Exception as e:
                    problems.append(f"{a.get('name')}: invalid model mapping — {e}")
                    continue
                if mid in seen:
                    continue
                seen.add(mid)
                probe = probe_chat_completion(
                    settings,
                    mid,
                    timeout_sec=min(12.0, float(getattr(settings, "bifrost_timeout_sec", 120)) / 4),
                )
                if not probe.get("ok"):
                    problems.append(
                        f"{a.get('name')} model '{mid}' chat completion failed: "
                        + (probe.get("error") or f"HTTP {probe.get('http_status')}")
                    )

    if not problems:
        return "live", []

    if wants == "live":
        raise HTTPException(422, "live mode unavailable — " + "; ".join(problems))

    # auto → explicit simulated with reasons (never label simulated as live)
    return "simulated", problems


def resolve_task_pairs(
    store: Store,
    benchmark_id: str,
    task_ids: list[str] | None,
    *,
    mode: str,
) -> list[tuple[dict, str | None]]:
    """Resolve the exact task set for a run.

    Validates every selected id belongs to the benchmark. In live mode every
    selected task must have hidden tests.
    """
    all_pairs = store.tasks_with_hidden(benchmark_id)
    by_id = {t["id"]: (t, h) for t, h in all_pairs}

    if task_ids is None:
        selected = list(all_pairs)
    else:
        selected = []
        missing = []
        wrong_bench = []
        for tid in task_ids:
            if tid not in by_id:
                # Could be unknown or belongs to another benchmark
                other = store.get_task(tid)
                if other is None:
                    missing.append(tid)
                else:
                    wrong_bench.append(tid)
            else:
                selected.append(by_id[tid])
        if missing:
            raise HTTPException(422, f"unknown task_ids: {', '.join(missing)}")
        if wrong_bench:
            raise HTTPException(
                422,
                f"task_ids not in benchmark '{benchmark_id}': {', '.join(wrong_bench)}",
            )
        if not selected:
            raise HTTPException(422, "no tasks selected")

    if mode == "live":
        ungradable = [t["id"] for t, h in selected if not h]
        if ungradable:
            raise HTTPException(
                422,
                "live mode requires hidden tests on every selected task; missing for: "
                + ", ".join(ungradable),
            )

    return selected


def create_run(store: Store, settings: Settings, body: RunCreate) -> dict:
    bench = store.get_benchmark(body.benchmark_id)
    if bench is None:
        raise HTTPException(422, f"unknown benchmark '{body.benchmark_id}'")

    agents: list[dict] = []
    for aid in body.agent_ids:
        a = store.get_agent(aid)
        if a is None:
            raise HTTPException(422, f"unknown agent '{aid}'")
        if not a.get("enabled", True):
            raise HTTPException(422, f"agent '{aid}' is disabled")
        agents.append(a)

    cfg = body.fairness.model_dump()
    isolation_requested = cfg["isolation"]
    isolation_note = None

    # Resolve gradable count for mode selection using the requested task set
    # (full benchmark if task_ids omitted).
    preview_pairs = resolve_task_pairs(store, body.benchmark_id, body.task_ids, mode="simulated")
    gradable = sum(1 for _, h in preview_pairs if h)

    mode, mode_reasons = pick_mode(settings, agents, gradable, isolation=isolation_requested)

    # Live isolation: never silently weaken security.
    if mode == "live" and isolation_requested == "docker":
        if not docker_available():
            if settings.allow_host_sandbox:
                cfg["isolation"] = "subprocess"
                isolation_note = (
                    "Docker unavailable; isolation downgraded to subprocess because "
                    "BIFROST_ALLOW_HOST_SANDBOX=1 (development only, unsafe for untrusted code)."
                )
            else:
                raise HTTPException(
                    422,
                    "live docker isolation requires Docker. Start Docker, or set "
                    "BIFROST_ALLOW_HOST_SANDBOX=1 for development-only subprocess grading "
                    "(unsafe for untrusted code).",
                )

    pairs = resolve_task_pairs(store, body.benchmark_id, body.task_ids, mode=mode)
    task_ids = [t["id"] for t, _ in pairs]
    ds_hash = fairness.dataset_hash(pairs)
    total_executions = len(task_ids) * len(agents) * cfg["repeats"]

    observed_preview = {
        "mode": mode,
        "hash_before": ds_hash,
        "hash_after": ds_hash,
        "mode_reasons": mode_reasons,
        "isolation_requested": isolation_requested,
        "isolation_used": cfg["isolation"],
    }
    if isolation_note:
        observed_preview["isolation_note"] = isolation_note

    preview = fairness.build_report(cfg, agents, observed_preview)
    if isolation_note:
        # Surface the downgrade in the fairness report checks.
        preview.setdefault("checks", []).append({
            "id": "isolation_downgrade",
            "label": "Sandbox isolation",
            "detail": isolation_note,
            "status": "warn",
        })
        preview.setdefault("violations", []).append(isolation_note)

    notes = body.notes or ""
    if mode == "simulated" and not notes.startswith("[SIMULATED]"):
        notes = ("[SIMULATED] " + notes).strip()

    doc = {
        "id": "",
        "name": body.name or "",
        "benchmark_id": bench["id"],
        "benchmark_name": bench["name"],
        "agent_ids": body.agent_ids,
        "task_ids": task_ids,
        "task_count": len(task_ids),
        "dataset_hash": ds_hash,
        "total_executions": total_executions,
        "agent_results": [],
        "status": "queued",
        "fairness": cfg,
        "fairness_report": preview,
        "started_at": now_iso(),
        "finished_at": None,
        "duration_sec": None,
        "progress": 0,
        "notes": notes,
        "created_by": "api",
        "execution_mode": mode,
        "mode_reasons": mode_reasons,
        "isolation_requested": isolation_requested,
        "isolation_note": isolation_note,
    }
    return store.insert_run(doc, mode)
