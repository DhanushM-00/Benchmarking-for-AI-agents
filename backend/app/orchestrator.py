"""Benchmark orchestrator.

Per run: resolve the task set -> hash it -> for each repeat, shuffle with the shared seed -> for each task
dispatch the identical prompt to every agent concurrently -> aggregate (median of repeats) -> re-hash the
dataset -> build the parity report from what was *observed*.
"""
from __future__ import annotations

import random
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import fairness, scoring
from .db import Store
from .executors import LiveExecutor, SimulatedExecutor


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Orchestrator:
    def __init__(self, store: Store, settings):
        self.store, self.settings = store, settings
        self.pool = ThreadPoolExecutor(max_workers=max(1, settings.max_parallel_runs), thread_name_prefix="run")
        self.cancel_flags: dict[str, threading.Event] = {}

    # -- public ----------------------------------------------------------------
    def submit(self, run_id: str) -> None:
        self.cancel_flags[run_id] = threading.Event()
        self.pool.submit(self._execute, run_id)

    def cancel(self, run_id: str) -> None:
        flag = self.cancel_flags.get(run_id)
        if flag:
            flag.set()

    def run_sync(self, run_id: str) -> None:  # used by the demo seeder and tests
        self.cancel_flags[run_id] = threading.Event()
        self._execute(run_id)

    # -- internals -------------------------------------------------------------
    def _event(self, run_id: str, type_: str, message: str | None = None, **kw) -> None:
        doc = {
            "type": type_,
            "run_id": run_id,
            "ts": now_iso(),
            "message": message or type_.replace("_", " "),
            "status": kw.pop("status", "ok"),
        }
        doc.update(kw)
        self.store.add_event(run_id, doc)

    def _execute(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        if run is None or run["status"] != "queued":
            return
        mode = self.store.get_run_mode(run_id)
        flag = self.cancel_flags[run_id]
        t0 = time.monotonic()
        try:
            cfg = run["fairness"]
            agents = []
            for aid in run["agent_ids"]:
                a = self.store.get_agent(aid)
                if a is None:
                    raise RuntimeError(f"agent '{aid}' disappeared after run creation")
                agents.append(a)

            # Prefer the exact task set persisted at create time for reproducibility.
            all_pairs = self.store.tasks_with_hidden(run["benchmark_id"])
            by_id_all = {t["id"]: (t, h) for t, h in all_pairs}
            stored_ids = run.get("task_ids")
            if stored_ids:
                pairs = []
                for tid in stored_ids:
                    if tid not in by_id_all:
                        raise RuntimeError(f"task '{tid}' missing from catalogue mid-run")
                    pairs.append(by_id_all[tid])
            else:
                pairs = list(all_pairs)
                if mode == "live":
                    pairs = [(t, h) for t, h in pairs if h]
            task_ids = [t["id"] for t, _ in pairs]
            by_id = {t["id"]: (t, h) for t, h in pairs}
            executor = LiveExecutor(self.settings) if mode == "live" else SimulatedExecutor()
            # Thread-safe event sink shared by concurrent agent workers
            def _sink(type_, message, **fields):
                self._event(run_id, type_, message, **fields)
            def _model_call_sink(doc: dict):
                doc = dict(doc)
                doc["run_id"] = run_id
                self.store.add_model_call(doc)
                # also emit a compact event for the event log
                self._event(
                    run_id,
                    "model_call_recorded",
                    f"{doc.get('agent_id')} {doc.get('phase') or 'call'} "
                    f"{'ok' if doc.get('success') else 'error'} "
                    f"tokens={doc.get('total_tokens')} latency_ms={doc.get('latency_ms')}",
                    agent_id=doc.get("agent_id"),
                    task_id=doc.get("task_id"),
                    status="ok" if doc.get("success") else "error",
                    duration_ms=doc.get("latency_ms"),
                    gateway_request_id=doc.get("gateway_request_id"),
                    metadata={"model_call_id": doc.get("id"), "model": doc.get("model")},
                )
            cfg = dict(cfg)
            cfg["_event_sink"] = _sink
            cfg["_model_call_sink"] = _model_call_sink
            cfg["_run_id"] = run_id


            run.update(status="running", started_at=now_iso(), progress=0)
            self.store.update_run(run)
            self._event(run_id, "run_started", f"run started mode={mode} tasks={len(task_ids)}", mode=mode, tasks=len(task_ids), agents=[a["id"] for a in agents], status="running")

            observed = {"mode": mode, "hash_before": fairness.dataset_hash(pairs), "dispatch": {a["id"]: [] for a in agents},
                        "prompt_hashes": {}, "timeouts": 0, "over_budget": 0,
                        "isolation_used": cfg["isolation"], "network_blocked": cfg["network_policy"] == "none",
                        "strategies": {a["id"]: None for a in agents}}
            results = {a["id"]: {} for a in agents}  # agent -> repeat -> task -> TaskResult
            total_units = cfg["repeats"] * len(task_ids)
            done_units, cancelled = 0, False
            downgraded = False

            for rep in range(cfg["repeats"]):
                order = list(task_ids)
                if cfg["randomize_task_order"]:
                    random.Random(cfg["random_seed"] + rep).shuffle(order)
                for a in agents:
                    observed["dispatch"][a["id"]].append(list(order))
                    results[a["id"]][rep] = {}
                for tid in order:
                    if flag.is_set():
                        cancelled = True
                        break
                    task, hidden = by_id[tid]
                    with ThreadPoolExecutor(max_workers=len(agents)) as tp:
                        futs = [(a, tp.submit(executor.run_task, a, task, hidden, cfg, rep)) for a in agents]
                        outs = [(a, f.result()) for a, f in futs]
                    for a, (res, meta) in outs:
                        results[a["id"]][rep][tid] = res
                        observed["prompt_hashes"].setdefault(tid, set()).add(meta["prompt_hash"])
                        observed["timeouts"] += bool(meta.get("timed_out"))
                        observed["over_budget"] += bool(meta.get("over_budget"))
                        if meta.get("strategy"):
                            observed["strategies"][a["id"]] = meta["strategy"]
                        if mode == "live":
                            if meta["isolation_used"] != cfg["isolation"]:
                                downgraded = True
                            observed["isolation_used"] = meta["isolation_used"]
                            observed["network_blocked"] = meta["network_blocked"]
                        self._event(
                            run_id, "task_completed",
                            f"{a['id']} finished {tid} completed={res['completed']} score={res['correctness']}",
                            agent_id=a["id"], task_id=tid, repeat=rep + 1,
                            completed=res["completed"], correctness=res["correctness"],
                            execution_time_sec=res["execution_time_sec"],
                            status="ok" if res["completed"] else "error",
                            duration_ms=int(float(res.get("execution_time_sec") or 0) * 1000),
                            gateway_request_id=res.get("gateway_request_id") or meta.get("gateway_request_id"),
                        )
                    done_units += 1
                    run["progress"] = max(run["progress"], min(99, round(done_units / total_units * 100)))
                    run["agent_results"] = [scoring.aggregate_agent(a, task_ids, results[a["id"]], cfg, "running")
                                            for a in agents]
                    self.store.update_run(run)
                    if mode == "simulated" and self.settings.sim_delay_ms:
                        time.sleep(self.settings.sim_delay_ms / 1000)
                if cancelled:
                    break

            # Re-hash the exact task set that was executed (not the whole benchmark).
            observed["hash_after"] = fairness.dataset_hash(pairs)
            if downgraded:
                observed["isolation_used"] = "subprocess" if cfg.get("isolation") == "docker" else observed["isolation_used"]

            if cancelled:
                status = "cancelled"
            else:
                status = "completed"

            run["agent_results"] = [scoring.aggregate_agent(a, task_ids, results[a["id"]], cfg, status) for a in agents]
            run["fairness_report"] = fairness.build_report(cfg, agents, observed)
            run["task_ids"] = task_ids
            run["task_count"] = len(task_ids)
            run["dataset_hash"] = observed.get("hash_before") or run.get("dataset_hash")
            run.update(
                status=status,
                finished_at=now_iso(),
                duration_sec=round(time.monotonic() - t0),
                progress=run["progress"] if cancelled else 100,
            )
            if mode == "simulated" and not str(run.get("notes") or "").startswith("[SIMULATED]"):
                run["notes"] = ("[SIMULATED] " + (run.get("notes") or "")).strip()
            self.store.update_run(run)
            self._event(run_id, f"run_{status}", progress=run["progress"], mode=mode)
        except Exception as e:  # never leave a run stuck in 'running'
            traceback.print_exc()
            run = self.store.get_run(run_id) or run
            run.update(status="failed", finished_at=now_iso(), duration_sec=round(time.monotonic() - t0),
                       notes=(run.get("notes", "") + f" [failed: {type(e).__name__}: {e}]").strip())
            self.store.update_run(run)
            self._event(run_id, "run_failed", error=f"{type(e).__name__}: {e}")
        finally:
            self.cancel_flags.pop(run_id, None)
