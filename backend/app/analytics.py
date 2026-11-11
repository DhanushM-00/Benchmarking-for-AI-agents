"""Failure analytics, recovery metrics, and agent comparison from *stored* runs.

All numbers are derived from run documents, task results, and model_call rows.
Unavailable metrics stay null. Incomplete runs are never treated as successful.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


# Canonical failure taxonomy
FAILURE_CATEGORIES = (
    "bifrost_gateway",
    "provider_model",
    "tool_execution",
    "invalid_tool_args",
    "agent_logic",
    "timeout",
    "hidden_test",
    "sandbox",
    "evaluation",
    "budget",
    "rate_limit",
    "unknown",
)


def classify_failure(
    *,
    error: str | None,
    error_category: str | None,
    isolation_used: str | None = None,
    timed_out: bool = False,
    tool_calls: list[dict] | None = None,
) -> str:
    """Map a failed task result into a structured category. Not everything is agent_logic."""
    msg = (error or "").lower()
    cat = (error_category or "").lower()

    if timed_out or cat == "timeout" or "timeout" in msg:
        return "timeout"
    if cat == "rate_limit" or "429" in msg or "rate limit" in msg:
        return "rate_limit"
    if cat == "budget" or "budget" in msg or "token budget" in msg:
        return "budget"
    if isolation_used == "unavailable" or "sandbox unavailable" in msg or "refusing to execute" in msg:
        return "sandbox"
    if "sandbox" in msg and ("crash" in msg or "error" in msg or "timed" in msg):
        return "sandbox"
    if cat == "model_api" or "bifrost" in msg or "gateway" in msg:
        if "unavailable" in msg or "connect" in msg or "timeout" in msg:
            return "bifrost_gateway"
        return "provider_model"
    if "model api" in msg or "http 5" in msg or "empty candidate" in msg:
        return "provider_model"
    if cat == "tool" or "tool" in msg:
        if "invalid" in msg or "arguments" in msg or "unknown tool" in msg:
            return "invalid_tool_args"
        return "tool_execution"
    if tool_calls:
        bad = [c for c in tool_calls if c.get("outcome") in ("error", "rejected")]
        if bad and not any(c.get("tool") == "model_call" for c in bad):
            if any("invalid" in str(c).lower() for c in bad):
                return "invalid_tool_args"
            return "tool_execution"
    if cat == "invalid_output" or "no code" in msg or "format" in msg:
        return "agent_logic"
    if cat == "incorrect" or "tests failed" in msg or "unit test" in msg:
        return "hidden_test"
    if "evaluation" in msg or "scorer" in msg:
        return "evaluation"
    if cat in FAILURE_CATEGORIES:
        return cat
    if error:
        return "unknown"
    return "hidden_test"  # failed without message but incomplete tests


def classify_model_call(call: dict) -> str:
    """Classify a failed model-call row. Success is not a failure category."""
    err = (call.get("error") or "").lower()
    status = call.get("http_status")
    if status == 429 or "429" in err or "rate limit" in err:
        return "rate_limit"
    if "timeout" in err:
        return "timeout"
    if any(s in err for s in ("unavailable", "connect", "gateway", "connection")):
        return "bifrost_gateway"
    return "provider_model"


def _provider_rates_from_model_calls(calls: list[dict]) -> list[dict]:
    by: dict[str, dict] = {}
    for c in calls:
        prov = c.get("provider") or "unknown"
        slot = by.setdefault(prov, {
            "provider": prov, "calls": 0, "failures": 0, "source": "model_calls",
        })
        slot["calls"] += 1
        if not c.get("success"):
            slot["failures"] += 1
    out = []
    for s in by.values():
        s["failure_rate"] = round(100.0 * s["failures"] / s["calls"], 1) if s["calls"] else None
        out.append(s)
    return sorted(out, key=lambda x: x["provider"])


def _iter_task_results(runs: list[dict], *, completed_only: bool = False):
    for run in runs:
        if completed_only and run.get("status") != "completed":
            continue
        if run.get("status") not in ("completed", "failed", "cancelled", "running"):
            continue
        for ar in run.get("agent_results") or []:
            for tr in ar.get("task_results") or []:
                yield run, ar, tr


def extract_failures(runs: list[dict]) -> list[dict]:
    """Structured failure records from stored task results."""
    out: list[dict] = []
    for run, ar, tr in _iter_task_results(runs):
        if tr.get("completed"):
            # recovered successes still count as a prior failure path if recovered flag set
            if not tr.get("recovered"):
                continue
        error = tr.get("error")
        if tr.get("completed") and not error and not tr.get("recovered"):
            continue
        if tr.get("completed") and tr.get("recovered"):
            # recovery success: record the recovered failure as informational
            category = "hidden_test"
            recovery_attempted = True
            recovery_result = "success"
        else:
            category = classify_failure(
                error=error,
                error_category=tr.get("error_category"),
                timed_out=bool(tr.get("timed_out")),
                tool_calls=tr.get("tool_calls"),
            )
            repairs = int(tr.get("repair_attempts") or 0)
            recovery_attempted = repairs > 0 or bool(tr.get("recovered"))
            recovery_result = (
                "success" if tr.get("recovered") and tr.get("completed")
                else ("failed" if recovery_attempted else "none")
            )
        out.append({
            "run_id": run.get("id"),
            "benchmark_id": run.get("benchmark_id"),
            "agent_id": ar.get("agent_id") or ar.get("id"),
            "agent_name": ar.get("agent_name") or ar.get("name"),
            "task_id": tr.get("task_id"),
            "category": category,
            "error": error,
            "timestamp": run.get("completed_at") or run.get("started_at"),
            "recovery_attempted": recovery_attempted if not tr.get("completed") or tr.get("recovered") else bool(tr.get("repair_attempts")),
            "recovery_result": recovery_result if not tr.get("completed") or tr.get("recovered") else (
                "success" if tr.get("recovered") else ("failed" if int(tr.get("repair_attempts") or 0) > 0 else "none")
            ),
            "repair_attempts": int(tr.get("repair_attempts") or 0),
            "strategy": tr.get("strategy") or ar.get("strategy"),
            "model": ar.get("model"),
            "provider": ar.get("model_provider") or ar.get("provider"),
        })
    return out


def recovery_analytics(
    runs: list[dict],
    failures: list[dict] | None = None,
    model_calls: list[dict] | None = None,
) -> dict:
    """Recovery and failure rates.

    Denominators (completed runs only, unless noted):
    - total_failures: task results with completed=false. A recovered success is not a failure.
    - recovery_attempts: tasks with repair_attempts>0 or recovered=true.
    - successful_recoveries: recovered=true AND completed=true.
    - failed_recoveries: recovery was attempted AND completed=false.
    - recovery_rate: 100 * successful_recoveries / recovery_attempts, or null if no attempt.
    - average_retries_per_task: sum(repair_attempts) / task count, or null if no tasks.
    - failure_rate_by_agent: 100 * not-completed / tasks for that agent.
    - failure_rate_by_tool: 100 * error|rejected tool calls / tool calls.
    - failure_rate_by_provider: from model-call records only
      (100 * unsuccessful calls / calls). Never inferred from task failures.
      Null source when model calls were not supplied.
    """
    failures = failures if failures is not None else extract_failures(runs)
    # Permanent failures exclude recovered successes.
    failed_tasks = [f for f in failures if f.get("recovery_result") != "success"]
    recovered_ok = [f for f in failures if f.get("recovery_result") == "success"]
    attempted = [f for f in failures if f.get("recovery_attempted")]
    successful_recoveries = len(recovered_ok)
    failed_recoveries = sum(1 for f in attempted if f.get("recovery_result") == "failed")
    total_retries = sum(int(f.get("repair_attempts") or 0) for f in failures)

    denom_attempts = len(attempted) or None
    recovery_rate = (
        round(100.0 * successful_recoveries / denom_attempts, 1) if denom_attempts else None
    )

    # Per-agent failure rates from completed runs only
    agent_stats: dict[str, dict] = {}
    for run, ar, tr in _iter_task_results(runs, completed_only=True):
        aid = ar.get("agent_id") or ar.get("id")
        slot = agent_stats.setdefault(aid, {
            "agent_id": aid, "tasks": 0, "failures": 0, "retries": 0,
            "recoveries": 0, "recovery_attempts": 0,
        })
        slot["tasks"] += 1
        if not tr.get("completed"):
            slot["failures"] += 1
        repairs = int(tr.get("repair_attempts") or 0)
        slot["retries"] += repairs
        if tr.get("recovered") and tr.get("completed"):
            slot["recoveries"] += 1
        if repairs > 0 or tr.get("recovered"):
            slot["recovery_attempts"] += 1
    for s in agent_stats.values():
        s["failure_rate"] = round(100.0 * s["failures"] / s["tasks"], 1) if s["tasks"] else None
        s["recovery_rate"] = (
            round(100.0 * s["recoveries"] / s["recovery_attempts"], 1)
            if s["recovery_attempts"] else None
        )

    # Tool failure rates
    tool_fail: dict[str, int] = defaultdict(int)
    tool_total: dict[str, int] = defaultdict(int)
    for run, ar, tr in _iter_task_results(runs, completed_only=True):
        for c in tr.get("tool_calls") or []:
            name = c.get("tool") or "unknown"
            tool_total[name] += 1
            if c.get("outcome") in ("error", "rejected"):
                tool_fail[name] += 1
    by_tool = [
        {
            "tool": k,
            "total": tool_total[k],
            "failures": tool_fail.get(k, 0),
            "failure_rate": round(100.0 * tool_fail.get(k, 0) / tool_total[k], 1) if tool_total[k] else None,
        }
        for k in sorted(tool_total)
    ]

    if model_calls is None:
        by_provider_out: list[dict] = []
        provider_source = "unavailable"
    else:
        by_provider_out = _provider_rates_from_model_calls(model_calls)
        provider_source = "model_calls"

    task_count = sum(1 for _ in _iter_task_results(runs, completed_only=True))
    avg_retries = round(total_retries / task_count, 3) if task_count else None

    model_fail_cats = _count_by(
        [{"category": classify_model_call(c)} for c in (model_calls or []) if not c.get("success")],
        "category",
    )

    return {
        "total_failures": len(failed_tasks),
        "total_retries": total_retries,
        "successful_recoveries": successful_recoveries,
        "failed_recoveries": failed_recoveries,
        "recovery_attempts": len(attempted),
        "recovery_rate": recovery_rate,
        "average_retries_per_task": avg_retries,
        "failure_rate_by_agent": list(agent_stats.values()),
        "failure_rate_by_tool": by_tool,
        "failure_rate_by_provider": by_provider_out,
        "provider_failure_source": provider_source,
        "failures_by_category": _count_by(failed_tasks, "category"),
        "model_call_failures_by_category": model_fail_cats,
        "formulas": {
            "total_failures": "completed-run task results with completed=false (recovered successes excluded)",
            "recovery_rate": "100 * successful_recoveries / recovery_attempts; null if no attempt was recorded",
            "successful_recoveries": "recovered=true and completed=true",
            "failed_recoveries": "recovery attempted and completed=false",
            "average_retries_per_task": "sum(repair_attempts) / task count on completed runs",
            "failure_rate_by_provider": "100 * failed model calls / model calls, grouped by provider; not inferred from tasks",
        },
    }


def _count_by(rows: list[dict], key: str) -> list[dict]:
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[str(r.get(key) or "unknown")] += 1
    return [{"key": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]


def agent_comparison(runs: list[dict], *, benchmark_id: str | None = None) -> dict:
    """Compare agents on completed runs only; identical-task fairness notes included."""
    completed = [r for r in runs if r.get("status") == "completed"]
    if benchmark_id:
        completed = [r for r in completed if r.get("benchmark_id") == benchmark_id]

    fairness_warnings: list[str] = []
    if not completed:
        fairness_warnings.append("No completed runs — comparison unavailable.")
        return {"agents": [], "fairness_warnings": fairness_warnings, "runs_used": 0}

    # Check comparable task sets across agents within each run
    for run in completed:
        ars = run.get("agent_results") or []
        task_sets = []
        for ar in ars:
            tids = tuple(sorted(t.get("task_id") for t in ar.get("task_results") or []))
            task_sets.append(tids)
        if len(set(task_sets)) > 1:
            fairness_warnings.append(
                f"Run {run.get('id')}: agents evaluated on different task sets."
            )
        fr = run.get("fairness_report") or {}
        if fr.get("violations"):
            fairness_warnings.append(
                f"Run {run.get('id')}: fairness violations: {', '.join(fr['violations'])}"
            )
        if (run.get("mode") or fr.get("mode")) == "simulated":
            fairness_warnings.append(
                f"Run {run.get('id')}: simulated mode — not measured live model performance."
            )

    # Aggregate per agent across runs
    buckets: dict[str, dict] = {}
    for run, ar, tr in _iter_task_results(completed, completed_only=True):
        aid = ar.get("agent_id") or ar.get("id")
        b = buckets.setdefault(aid, {
            "agent_id": aid,
            "agent_name": ar.get("agent_name") or ar.get("name") or aid,
            "strategy": tr.get("strategy") or ar.get("strategy"),
            "model": ar.get("model"),
            "provider": ar.get("model_provider") or ar.get("provider"),
            "tasks": 0,
            "successes": 0,
            "hidden_passed": 0,
            "hidden_total": 0,
            "exec_time": [],
            "tokens_in": [],
            "tokens_out": [],
            "tool_calls": [],
            "steps": [],
            "retries": [],
            "recoveries": 0,
            "recovery_opportunities": 0,
            "cost_success": [],
            "cost_all": [],
        })
        b["tasks"] += 1
        ok = bool(tr.get("completed"))
        if ok:
            b["successes"] += 1
        b["hidden_passed"] += int(tr.get("unit_tests_passed") or 0)
        b["hidden_total"] += int(tr.get("unit_tests_total") or 0)
        if tr.get("execution_time_sec") is not None:
            b["exec_time"].append(float(tr["execution_time_sec"]))
        if tr.get("tokens_input") is not None:
            b["tokens_in"].append(int(tr["tokens_input"]))
        if tr.get("tokens_output") is not None:
            b["tokens_out"].append(int(tr["tokens_output"]))
        calls = tr.get("tool_calls") or []
        b["tool_calls"].append(len(calls))
        steps = tr.get("model_calls")
        b["steps"].append(int(steps) if steps is not None else len(tr.get("agent_steps") or []))
        repairs = int(tr.get("repair_attempts") or 0)
        b["retries"].append(repairs)
        if repairs > 0 or tr.get("recovered") or not ok:
            b["recovery_opportunities"] += 1 if (repairs > 0 or tr.get("recovered")) else 0
        if tr.get("recovered"):
            b["recoveries"] += 1
        cost = tr.get("cost_usd")
        if cost is not None:
            b["cost_all"].append(float(cost))
            if ok:
                b["cost_success"].append(float(cost))

    agents = []
    for aid, b in buckets.items():
        n = b["tasks"] or None
        agents.append({
            "agent_id": aid,
            "agent_name": b["agent_name"],
            "strategy": b["strategy"],
            "model": b["model"],
            "provider": b["provider"],
            "tasks": b["tasks"],
            "task_success_rate": round(100.0 * b["successes"] / n, 1) if n else None,
            "hidden_test_pass_rate": (
                round(100.0 * b["hidden_passed"] / b["hidden_total"], 1)
                if b["hidden_total"] else None
            ),
            "avg_execution_time_sec": round(sum(b["exec_time"]) / len(b["exec_time"]), 3) if b["exec_time"] else None,
            "avg_tokens_input": round(sum(b["tokens_in"]) / len(b["tokens_in"]), 1) if b["tokens_in"] else None,
            "avg_tokens_output": round(sum(b["tokens_out"]) / len(b["tokens_out"]), 1) if b["tokens_out"] else None,
            "total_tokens": (sum(b["tokens_in"]) + sum(b["tokens_out"])) if (b["tokens_in"] or b["tokens_out"]) else None,
            "avg_tool_calls": round(sum(b["tool_calls"]) / n, 2) if n else None,
            "avg_execution_steps": round(sum(b["steps"]) / n, 2) if n else None,
            "retry_rate": round(100.0 * sum(1 for x in b["retries"] if x > 0) / n, 1) if n else None,
            "recovery_rate": (
                round(100.0 * b["recoveries"] / b["recovery_opportunities"], 1)
                if b["recovery_opportunities"] else None
            ),
            # Total operational spend (incl. failed attempts) / successful tasks
            "cost_per_successful_task": (
                round(sum(b["cost_all"]) / b["successes"], 6)
                if b["successes"] and b["cost_all"] else None
            ),
            "total_cost_usd": round(sum(b["cost_all"]), 6) if b["cost_all"] else None,
        })

    agents.sort(key=lambda a: (-(a["task_success_rate"] or -1), a["agent_name"] or ""))
    return {
        "agents": agents,
        "fairness_warnings": fairness_warnings,
        "runs_used": len(completed),
        "benchmark_id": benchmark_id,
    }


def category_comparison(runs: list[dict]) -> list[dict]:
    """Success rate by task category (benchmark_id prefix / task id prefix)."""
    stats: dict[str, dict] = {}
    for run, ar, tr in _iter_task_results(runs, completed_only=True):
        tid = tr.get("task_id") or ""
        cat = tid.rsplit("-t", 1)[0] if "-t" in tid else (run.get("benchmark_id") or "unknown")
        aid = ar.get("agent_id") or ar.get("id")
        key = (cat, aid)
        slot = stats.setdefault(key, {"category": cat, "agent_id": aid, "tasks": 0, "successes": 0})
        slot["tasks"] += 1
        if tr.get("completed"):
            slot["successes"] += 1
    out = []
    for s in stats.values():
        s["success_rate"] = round(100.0 * s["successes"] / s["tasks"], 1) if s["tasks"] else None
        out.append(s)
    return sorted(out, key=lambda x: (x["category"], x["agent_id"]))


def historical_comparison(runs: list[dict], limit: int = 20) -> list[dict]:
    completed = [r for r in runs if r.get("status") == "completed"]
    completed = sorted(
        completed,
        key=lambda r: r.get("completed_at") or r.get("started_at") or "",
        reverse=True,
    )[:limit]
    rows = []
    for run in completed:
        ars = run.get("agent_results") or []
        rows.append({
            "run_id": run.get("id"),
            "benchmark_id": run.get("benchmark_id"),
            "started_at": run.get("started_at"),
            "completed_at": run.get("completed_at"),
            "mode": run.get("mode"),
            "agents": [
                {
                    "agent_id": a.get("agent_id") or a.get("id"),
                    "overall_score": a.get("overall_score"),
                    "task_success": (a.get("metrics") or {}).get("task_success"),
                    "total_cost_usd": a.get("total_cost_usd"),
                    "total_tokens": a.get("total_tokens"),
                }
                for a in ars
            ],
            "fairness_score": (run.get("fairness_report") or {}).get("score"),
        })
    return rows


def build_analytics(
    runs: list[dict],
    *,
    benchmark_id: str | None = None,
    agent_id: str | None = None,
    provider: str | None = None,
    model_calls: list[dict] | None = None,
) -> dict:
    filtered = list(runs)
    if benchmark_id:
        filtered = [r for r in filtered if r.get("benchmark_id") == benchmark_id]
    failures = extract_failures(filtered)
    calls = list(model_calls) if model_calls is not None else None
    if agent_id:
        failures = [f for f in failures if f.get("agent_id") == agent_id]
        if calls is not None:
            calls = [c for c in calls if c.get("agent_id") == agent_id]
    if provider:
        failures = [f for f in failures if (f.get("provider") or "").lower() == provider.lower()]
        if calls is not None:
            calls = [c for c in calls if (c.get("provider") or "").lower() == provider.lower()]

    comparison = agent_comparison(filtered, benchmark_id=benchmark_id)
    if agent_id:
        comparison["agents"] = [a for a in comparison["agents"] if a["agent_id"] == agent_id]
    if provider:
        comparison["agents"] = [
            a for a in comparison["agents"]
            if (a.get("provider") or "").lower() == provider.lower()
        ]

    recovery = recovery_analytics(filtered, failures, model_calls=calls)
    return {
        "source": "stored_runs",
        "runs_scanned": len(filtered),
        "completed_runs": sum(1 for r in filtered if r.get("status") == "completed"),
        "failures": failures[:500],
        "failure_count": sum(1 for f in failures if f.get("recovery_result") != "success"),
        "recovery": recovery,
        "comparison": comparison,
        "category_comparison": category_comparison(filtered),
        "historical": historical_comparison(filtered),
        "data_quality": {
            "demo_data": False,
            "includes_incomplete_runs": any(r.get("status") != "completed" for r in filtered),
            "notes": [
                "Metrics use completed runs for rates; failures list includes all stored outcomes.",
                "Cost is null when no task recorded cost_usd.",
                "Recovery rate only uses tasks with a recorded recovery attempt.",
            ],
        },
    }


def build_benchmark_report(run: dict, model_calls: list[dict] | None = None) -> dict:
    """Evidence-backed report for a single stored run."""
    if not run:
        return {"error": "run not found"}
    cfg = run.get("fairness_config") or run.get("config") or {}
    agents = run.get("agent_results") or []
    failures = extract_failures([run])
    recovery = recovery_analytics([run], failures, model_calls=model_calls)
    comparison = agent_comparison([run] if run.get("status") == "completed" else [])

    total_tokens = sum(a.get("total_tokens") or 0 for a in agents)
    total_cost = sum(a.get("total_cost_usd") or 0 for a in agents)
    costs_known = any(a.get("total_cost_usd") is not None for a in agents)

    conclusions = []
    if run.get("status") != "completed":
        conclusions.append(f"Run status is '{run.get('status')}' — results are incomplete.")
    if comparison["agents"]:
        top = comparison["agents"][0]
        conclusions.append(
            f"Highest task success rate among agents in this run: "
            f"{top['agent_name']} at {top['task_success_rate']}% "
            f"over {top['tasks']} tasks."
        )
    if comparison["fairness_warnings"]:
        conclusions.append("Fairness warnings apply — see fairness_warnings.")
    if run.get("mode") == "simulated":
        conclusions.append("Simulated execution — not live Bifrost model measurements.")

    return {
        "run_id": run.get("id"),
        "status": run.get("status"),
        "mode": run.get("mode"),
        "benchmark_id": run.get("benchmark_id"),
        "configuration": {
            "repeats": cfg.get("repeats"),
            "time_limit_per_task_sec": cfg.get("time_limit_per_task_sec"),
            "max_tokens_per_task": cfg.get("max_tokens_per_task"),
            "isolation": cfg.get("isolation"),
            "network_policy": cfg.get("network_policy"),
            "temperature": cfg.get("temperature"),
        },
        "agents_tested": [
            {
                "agent_id": a.get("agent_id") or a.get("id"),
                "name": a.get("agent_name") or a.get("name"),
                "model": a.get("model"),
                "provider": a.get("model_provider") or a.get("provider"),
                "strategy": a.get("strategy"),
                "overall_score": a.get("overall_score"),
                "metrics": a.get("metrics"),
                "total_tokens": a.get("total_tokens"),
                "total_cost_usd": a.get("total_cost_usd"),
                "avg_execution_time_sec": a.get("avg_execution_time_sec"),
                "tasks": len(a.get("task_results") or []),
            }
            for a in agents
        ],
        "task_count": max((len(a.get("task_results") or []) for a in agents), default=0),
        "success_rate_by_agent": {
            (a.get("agent_id") or a.get("id")): (a.get("metrics") or {}).get("task_success")
            for a in agents
        },
        "token_consumption": total_tokens,
        "latency_avg_sec": (
            round(sum(a.get("avg_execution_time_sec") or 0 for a in agents) / len(agents), 3)
            if agents else None
        ),
        "cost_usd": round(total_cost, 6) if costs_known else None,
        "tool_usage": _tool_usage_for_run(run),
        "failure_analysis": {
            "failures": failures,
            "by_category": recovery.get("failures_by_category"),
        },
        "recovery_analysis": recovery,
        "fairness_warnings": comparison.get("fairness_warnings") or [],
        "fairness_report": run.get("fairness_report"),
        "conclusions": conclusions,
        "data_source": "stored_run",
    }


def _tool_usage_for_run(run: dict) -> list[dict]:
    counts: dict[str, dict] = {}
    for ar in run.get("agent_results") or []:
        for tr in ar.get("task_results") or []:
            for c in tr.get("tool_calls") or []:
                name = c.get("tool") or "unknown"
                slot = counts.setdefault(name, {"tool": name, "total": 0, "errors": 0})
                slot["total"] += 1
                if c.get("outcome") in ("error", "rejected"):
                    slot["errors"] += 1
    return sorted(counts.values(), key=lambda x: -x["total"])
