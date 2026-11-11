"""Scoring engine (scorer-2026.03.1): per-task scores, per-agent aggregation, leaderboard, dashboard."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict

from . import analytics as analytics_mod

METRICS = ("task_success", "correctness", "efficiency", "tool_usage", "consistency")
PALETTE = ["#5b8cff", "#2dd4a7", "#f5a524", "#a78bfa", "#f472b6"]


def r1(x: float) -> float: return round(x * 10) / 10
def r4(x: float) -> float: return round(x * 10000) / 10000
def r6(x: float) -> float: return round(x * 1000000) / 1000000
def clamp(x: float, lo: float, hi: float) -> float: return max(lo, min(hi, x))
def mean(xs: list[float]) -> float: return sum(xs) / len(xs) if xs else 0.0


def quantile(xs: list[float], q: float) -> float:
    """Linear-interpolated quantile (numpy default)."""
    if not xs:
        return 0.0
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


# ---- per-task scores -----------------------------------------------------
def efficiency_score(unnecessary_steps: int, exec_time: float, time_limit: float) -> float:
    return clamp(100 - unnecessary_steps * 7.5 - (exec_time / time_limit) * 28, 5, 100)


def tool_usage_score(tool_calls: list[dict], base: float = 100.0) -> float:
    errors = sum(1 for c in tool_calls if c["outcome"] == "error")
    rejected = sum(1 for c in tool_calls if c["outcome"] == "rejected")
    return clamp(base - errors * 20 - rejected * 10, 10, 100)


# ---- per-agent aggregation -----------------------------------------------
def _blend(m: dict[str, float], weights: dict[str, float]) -> float:
    """Blend of the four per-repeat metrics (consistency is derived *from* this)."""
    keys = [k for k in METRICS if k != "consistency"]
    total = sum(weights[k] for k in keys) or 1.0
    return sum(m[k] * weights[k] for k in keys) / total


def _repeat_metrics(results: list[dict]) -> dict[str, float]:
    return {
        "task_success": 100 * sum(1 for r in results if r["completed"]) / len(results),
        "correctness": mean([r["correctness"] for r in results]),
        "efficiency": mean([r["efficiency_score"] for r in results]),
        "tool_usage": mean([r["tool_usage_score"] for r in results]),
    }


def aggregate_agent(agent: dict, task_ids: list[str], by_repeat: dict[int, dict[str, dict]],
                    cfg: dict, status: str) -> dict:
    """Median-of-repeats report for one agent. `by_repeat[repeat][task_id] = TaskResult`."""
    weights = cfg["metric_weights"]
    reported: list[dict] = []
    for tid in task_ids:
        runs = [by_repeat[r][tid] for r in sorted(by_repeat) if tid in by_repeat[r]]
        if runs:
            runs.sort(key=lambda t: t["correctness"])
            reported.append(runs[(len(runs) - 1) // 2])  # median repeat for this task

    every = [t for r in by_repeat.values() for t in r.values()]
    full = [r for r in sorted(by_repeat) if len(by_repeat[r]) == len(task_ids)]
    per_repeat = [_blend(_repeat_metrics(list(by_repeat[r].values())), weights) for r in full]
    variance = statistics.pstdev(per_repeat) if len(per_repeat) >= 2 else 0.0
    # One repeat cannot measure stability: report a neutral 50 instead of rewarding it with 100.
    consistency = clamp(100 - variance * 2.1, 40, 100) if len(per_repeat) >= 2 else (50.0 if reported else 0.0)

    if reported:
        m = _repeat_metrics(reported)
        metrics = {k: r1(m[k]) for k in m} | {"consistency": r1(consistency)}
    else:
        metrics = {k: 0.0 for k in METRICS}
    times = [t["execution_time_sec"] for t in reported]
    overall = r1(sum(metrics[k] * weights[k] for k in METRICS))

    # Prefer reported fields when present so missing gateway usage is not treated as zero.
    def _tok(t: dict) -> int:
        if t.get("tokens_input_reported") is not None or t.get("tokens_output_reported") is not None:
            return int(t.get("tokens_input_reported") or 0) + int(t.get("tokens_output_reported") or 0)
        return int(t.get("tokens_input") or 0) + int(t.get("tokens_output") or 0)

    def _cost_val(t: dict) -> float | None:
        if "cost_usd_reported" in t:
            return t["cost_usd_reported"]
        c = t.get("cost_usd")
        return float(c) if c is not None else None

    token_sum = sum(_tok(t) for t in every)
    known_costs = [c for t in every if (c := _cost_val(t)) is not None]
    cost_total = r6(sum(known_costs)) if known_costs else None

    return {
        "agent_id": agent["id"], "agent_name": agent["name"], "color_index": agent["color_index"],
        "status": status,
        "tasks_completed": sum(1 for t in reported if t["completed"]), "tasks_total": len(task_ids),
        "task_results": reported, "metrics": metrics, "overall_score": overall,
        "avg_execution_time_sec": r1(mean(times)), "p95_execution_time_sec": r1(quantile(times, 0.95)),
        "total_tokens": token_sum,
        "total_cost_usd": cost_total if cost_total is not None else 0.0,
        "total_cost_usd_reported": cost_total,
        "cost_known": bool(known_costs),
        "tool_calls_total": sum(len(t["tool_calls"]) for t in reported),
        "unnecessary_steps_total": sum(t["unnecessary_steps"] for t in reported),
        "repeat_variance": r1(variance),
    }


# ---- leaderboard / dashboard ---------------------------------------------
def parity_locked(run: dict) -> bool:
    """Only completed runs with no failed integrity check enter the leaderboard."""
    return run["status"] == "completed" and not run["fairness_report"]["violations"]


def _board(runs: list[dict]) -> list[dict]:
    acc: dict[str, dict] = {}
    for run in runs:
        for ar in run["agent_results"]:
            e = acc.setdefault(ar["agent_id"], {"agent_id": ar["agent_id"], "agent_name": ar["agent_name"],
                                                "color_index": ar["color_index"], "_n": 0, "_sum": defaultdict(float),
                                                "total_tokens": 0, "total_cost_usd": 0.0})
            e["_n"] += 1
            for k in METRICS:
                e["_sum"][k] += ar["metrics"][k]
            for k in ("overall_score", "avg_execution_time_sec", "p95_execution_time_sec"):
                e["_sum"][k] += ar[k]
            e["total_tokens"] += ar["total_tokens"]
            e["total_cost_usd"] += ar["total_cost_usd"]
    out = []
    for e in acc.values():
        n, s = e["_n"], e["_sum"]
        out.append({
            "agent_id": e["agent_id"], "agent_name": e["agent_name"], "color_index": e["color_index"],
            "overall_score": r1(s["overall_score"] / n), **{k: r1(s[k] / n) for k in METRICS},
            "avg_execution_time_sec": r1(s["avg_execution_time_sec"] / n),
            "p95_execution_time_sec": r1(s["p95_execution_time_sec"] / n),
            "total_tokens": e["total_tokens"], "total_cost_usd": r6(e["total_cost_usd"]),
            "runs_count": n, "rank": 0, "delta_rank": 0,
        })
    out.sort(key=lambda x: (-x["overall_score"], x["agent_id"]))
    for i, e in enumerate(out):
        e["rank"] = i + 1
    return out


def build_leaderboard(runs: list[dict]) -> list[dict]:
    """`runs` newest-first. delta_rank = places gained since the most recent run was added."""
    locked = [r for r in runs if parity_locked(r)]
    board = _board(locked)
    prev = {e["agent_id"]: e["rank"] for e in _board(locked[1:])}
    for e in board:
        e["delta_rank"] = prev[e["agent_id"]] - e["rank"] if e["agent_id"] in prev else 0
    return board


def build_score_trend(runs: list[dict]) -> list[dict]:
    done = sorted((r for r in runs if r["status"] == "completed"), key=lambda r: r["started_at"])[-8:]
    return [{"label": r["benchmark_name"].split(" ")[0],
             **{ar["agent_name"]: ar["overall_score"] for ar in r["agent_results"]}} for r in done]


def build_dashboard(runs: list[dict], benchmarks: list[dict], model_calls: list[dict] | None = None) -> dict:
    completed = [r for r in runs if r["status"] == "completed"]
    results = [ar for r in completed for ar in r["agent_results"]]
    known_costs = [
        float(a["total_cost_usd_reported"])
        if a.get("total_cost_usd_reported") is not None
        else float(a["total_cost_usd"])
        for a in results
        if (a.get("total_cost_usd_reported") is not None)
        or (a.get("cost_known") is True)
        or (a.get("total_cost_usd") is not None and a.get("total_cost_usd") != 0)
    ]
    # Prefer explicit known costs; fall back to summed totals only when agents reported spend.
    cost = sum(known_costs) if known_costs else sum(float(a.get("total_cost_usd") or 0) for a in results)
    fair = [r["fairness_report"]["score"] for r in completed if r["fairness_report"]["score"] > 0]
    n = len(results)
    c = len(completed)
    ordered = sorted(completed, key=lambda r: r.get("completed_at") or r.get("started_at") or "")

    def _mean_score(run: dict) -> float | None:
        ars = run.get("agent_results") or []
        if not ars:
            return None
        return sum(a.get("overall_score") or 0 for a in ars) / len(ars)

    score_delta = None
    if len(ordered) >= 2:
        prev, last = _mean_score(ordered[-2]), _mean_score(ordered[-1])
        if prev is not None and last is not None:
            score_delta = r1(last - prev)

    checks_passing = checks_total = None
    if ordered:
        checks = (ordered[-1].get("fairness_report") or {}).get("checks") or []
        if checks:
            checks_passing = sum(1 for chk in checks if chk.get("status") == "pass")
            checks_total = len(checks)

    return {
        "stats": {
            "total_runs": len(runs), "completed_runs": c,
            "tasks_executed": sum(len(a["task_results"]) for a in results),
            "total_agent_executions": n,
            "total_cost_usd": round(cost, 6), "total_tokens": sum(a["total_tokens"] for a in results),
            "avg_overall_score": r1(sum(a["overall_score"] for a in results) / n) if n else None,
            "score_delta": score_delta,
            "avg_cost_per_run": round(cost / c, 6) if c else None,
            "avg_execution_time_sec": r1(sum(a["avg_execution_time_sec"] for a in results) / n) if n else None,
            "fairness_score": round(sum(fair) / len(fair)) if fair else None,
            "fairness_checks_passing": checks_passing,
            "fairness_checks_total": checks_total,
        },
        "recent_runs": runs[:6],
        "leaderboard": build_leaderboard(runs),
        "score_trend": build_score_trend(runs),
        "cost_by_benchmark": [
            {"name": b["name"], "color": PALETTE[i % len(PALETTE)],
             "value": round(sum(a["total_cost_usd"] for r in completed if r["benchmark_id"] == b["id"]
                                for a in r["agent_results"]), 2)}
            for i, b in enumerate(benchmarks)],
        "analytics": analytics_mod.build_analytics(runs, model_calls=model_calls),
        "data_source": "stored_runs",
        "demo_data": False,
    }
