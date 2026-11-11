"""Executors turn (agent, task) into a TaskResult. Two implementations share one interface:

  SimulatedExecutor  deterministic, seeded, no network, no sandbox — for demos and UI work.
  LiveExecutor       real model call -> hidden-test grading in the sandbox -> measured metrics.
"""
from __future__ import annotations

import random
from typing import Any

from . import scoring
from .adapters import SYSTEM_PROMPT
from .agents import agent_for
from .fairness import prompt_hash
from .sandbox import grade

PROFILES = {
    "atlas-coder": dict(completion=0.76, correctness=79, speed=1.0, tool_quality=84, tool_count=4, effort=1.0),
    "nova-coder": dict(completion=0.62, correctness=66, speed=0.61, tool_quality=71, tool_count=3, effort=0.72),
    "forge-coder": dict(completion=0.84, correctness=88, speed=1.48, tool_quality=91, tool_count=5, effort=1.35),
}
DIFF_ADJ = {"easy": 0.1, "medium": 0.0, "hard": -0.09, "expert": -0.17}


def _cost(agent: dict, tin: int, tout: int) -> float:
    return scoring.r6(tin / 1000 * agent["cost_per_1k_input"] + tout / 1000 * agent["cost_per_1k_output"])


def _task_result(task: dict, **kw: Any) -> dict:
    return {"task_id": task["id"], "task_title": task["title"], "category": task["category"],
            "difficulty": task["difficulty"], "error": None, **kw}


class SimulatedExecutor:
    mode = "simulated"

    def run_task(self, agent: dict, task: dict, hidden: str | None, cfg: dict, repeat: int) -> tuple[dict, dict]:
        # Per-(seed, agent, repeat, task) stream: reproducible, and repeats genuinely differ.
        rng = random.Random(f"{cfg['random_seed']}:{agent['id']}:{repeat}:{task['id']}")
        prof = PROFILES.get(agent["id"]) or dict(completion=0.7, correctness=72, speed=1.0, tool_quality=78,
                                                  tool_count=4, effort=1.0)
        adj = DIFF_ADJ[task["difficulty"]]
        p = min(0.97, max(0.05, prof["completion"] + adj))
        completed = rng.random() < p
        correctness = (min(100, max(30, prof["correctness"] + (rng.random() - 0.45) * 34 + adj * 60))
                       if completed else round(rng.random() * 28))
        tests = task["test_count"]
        exec_time = max(1.2, (9 + tests * 1.7) * prof["speed"] * (0.72 + rng.random() * 0.62) * (1 - adj * 0.6))
        tin = round(620 + tests * 46 + rng.random() * 520)
        tout = round((320 + tests * 128) * prof["effort"] * (0.6 + rng.random() * 0.9) * (1 if completed else 0.45))
        cached = round(tin * (0.12 + rng.random() * 0.3))

        names = [t["name"] for t in agent["tools"]] or ["fs_write"]
        n_calls = max(0, round(prof["tool_count"] * (0.6 + rng.random() * 0.9)))
        calls = []
        for _ in range(n_calls):
            tool, roll = rng.choice(names), rng.random()
            calls.append({
                "tool": tool,
                "args_summary": {"fs_read": "path=src/module.py", "fs_write": "path=solution.py",
                                 "shell": "cmd=pytest -q"}.get(tool, 'query="def main"'),
                "outcome": "error" if roll > 0.88 else "rejected" if roll > 0.82 else "success",
                "duration_ms": round(120 + rng.random() * 2400)})
        unnecessary = max(0, round((n_calls * 0.32 - (rng.random() * 1.6 - 0.2)) * prof["effort"]))
        limit = cfg["time_limit_per_task_sec"]
        eff = scoring.efficiency_score(unnecessary, exec_time, limit)
        tool_q = scoring.clamp(prof["tool_quality"] + (rng.random() - 0.5) * 22
                               - sum(1 for c in calls if c["outcome"] == "error") * 6, 10, 100)
        err = None if completed else (
            "Sandbox timeout — agent did not finish within the limit." if rng.random() > 0.5
            else "Tests failed; agent halted after max repair steps.")
        res = _task_result(
            task, completed=completed, correctness=scoring.r1(correctness),
            unit_tests_passed=round(correctness / 100 * tests), unit_tests_total=tests,
            execution_time_sec=scoring.r1(exec_time), tokens_input=tin, tokens_output=tout, tokens_cached=cached,
            cost_usd=_cost(agent, tin, tout), tool_calls=calls, unnecessary_steps=unnecessary,
            efficiency_score=scoring.r1(eff), tool_usage_score=scoring.r1(tool_q))
        res["error"] = err
        return res, {"prompt_hash": prompt_hash("", task["prompt"]),
            "task_prompt_hash": prompt_hash("", task["prompt"]),
            "model": agent.get("model"),
            "provider": agent.get("model_provider"),
                     "isolation_used": cfg["isolation"], "network_blocked": cfg["network_policy"] == "none"}


class LiveExecutor:
    mode = "live"

    def __init__(self, settings):
        self.settings = settings

    def run_task(self, agent: dict, task: dict, hidden: str | None, cfg: dict, repeat: int) -> tuple[dict, dict]:
        """Run a multi-strategy agent in a private workspace, then grade against hidden tests.

        Stage 2: Atlas=ReAct, Nova=Plan-Act-Verify, Forge=state machine.
        Model traffic still goes through Bifrost (Stage 1).
        """
        import tempfile
        from .agents.base import AgentRunConfig

        assert hidden, "live execution requires a hidden test suite"
        limit = cfg["time_limit_per_task_sec"]
        max_tokens = min(cfg["max_tokens_per_task"], task["max_tokens"])

        sink = cfg.get("_event_sink")
        agent_cfg = AgentRunConfig(
            temperature=cfg["temperature"],
            max_tokens_per_call=min(4096, max_tokens),
            time_limit_sec=float(limit),
            max_model_calls=int(cfg.get("max_model_calls", 12)),
            max_tool_calls=int(cfg.get("max_tool_calls", 40)),
            max_repair_attempts=int(cfg.get("max_repair_attempts", 3)),
            isolation=cfg["isolation"],
            network_policy=cfg["network_policy"],
            on_event=sink,
            on_model_call=cfg.get("_model_call_sink"),
            agent_id=agent.get("id"),
            task_id=task.get("id"),
            run_id=cfg.get("_run_id"),
        )

        with tempfile.TemporaryDirectory(prefix="bifrost-agent-") as tmp:
            strategy = agent_for(agent, self.settings)
            ar = strategy.run(task["prompt"], tmp, agent_cfg)

        meta = {
            "prompt_hash": prompt_hash("", task["prompt"]),
            "task_prompt_hash": prompt_hash("", task["prompt"]),
            "strategy_prompt_hash": prompt_hash(ar.strategy or "", ""),
            "isolation_used": cfg["isolation"],
            "network_blocked": cfg["network_policy"] == "none",
            "gateway_request_id": (ar.gateway_request_ids[0] if ar.gateway_request_ids else None),
            "gateway_request_ids": list(ar.gateway_request_ids),
            "model_used": ar.model_used or agent.get("model"),
            "provider_used": ar.provider_used or agent.get("model_provider"),
            "gateway_source": "bifrost",
            "agent_id": agent.get("id"),
            "task_id": task.get("id"),
            "strategy": ar.strategy,
            "model_calls": ar.model_calls,
            "repair_attempts": ar.repair_attempts,
            "error_category": ar.error_category,
            "recovered": ar.recovered,
            "agent_steps": ar.steps[:40],
        }

        passed, total, error, sandbox_time = 0, task["test_count"], ar.error, 0.0
        if ar.code and ar.status in ("ok", "failed", "budget_exhausted"):
            # Grade even partial solutions when code exists
            remaining = max(1, int(limit - ar.latency_sec))
            g = grade(
                ar.code,
                hidden,
                timeout_sec=remaining,
                isolation=cfg["isolation"],
                image=self.settings.docker_image,
                network_policy=cfg["network_policy"],
                memory_mb=self.settings.sandbox_memory_mb,
                require_docker=bool(getattr(self.settings, "require_docker", True))
                and not bool(getattr(self.settings, "allow_host_sandbox", False)),
            )
            passed, total, error, sandbox_time = g.passed, g.total, g.error, g.duration_sec
            meta.update(isolation_used=g.isolation_used, network_blocked=g.network_blocked, timed_out=g.timed_out)
            if g.timed_out:
                ar.error_category = ar.error_category or "timeout"
            if sink:
                try:
                    sink(
                        "hidden_tests_completed",
                        f"{passed}/{total} tests passed",
                        agent_id=agent.get("id"),
                        task_id=task.get("id"),
                        status="ok" if passed == total and not error else "error",
                        duration_ms=int(sandbox_time * 1000),
                        metadata={"passed": passed, "total": total, "error": error},
                    )
                except Exception:
                    pass

        exec_time = ar.latency_sec + sandbox_time
        over_tokens = (
            getattr(ar, "usage_known", False)
            and (ar.tokens_input + ar.tokens_output) > cfg["max_tokens_per_task"]
        )
        if over_tokens:
            passed, error = 0, "Token budget exceeded."
            meta["over_budget"] = True
            ar.error_category = "budget"
        if exec_time > limit:
            passed, error = 0, "Sandbox timeout — agent did not finish within the limit."
            meta["timed_out"] = True
            ar.error_category = ar.error_category or "timeout"

        correctness = 100 * passed / total if total else 0.0
        completed = total > 0 and passed == total and error is None
        calls = list(ar.tool_calls)

        # Cost priority: actual gateway cost > estimated from reported tokens + agent rates >
        # unavailable (never invent zero when usage was never reported).
        if ar.cost_usd_gateway is not None:
            cost: float | None = scoring.r6(ar.cost_usd_gateway)
            meta["cost_source"] = "gateway"
        elif getattr(ar, "usage_known", False) and (ar.tokens_input or ar.tokens_output):
            cost = _cost(agent, ar.tokens_input, ar.tokens_output)
            meta["cost_source"] = "estimated"
        elif getattr(ar, "usage_known", False):
            # Explicit zero usage from gateway
            cost = 0.0
            meta["cost_source"] = "estimated"
        else:
            cost = None
            meta["cost_source"] = None

        # Prefer null over fabricated zeros when the gateway never reported usage.
        tin_out = ar.tokens_input if getattr(ar, "usage_known", False) else None
        tout_out = ar.tokens_output if getattr(ar, "usage_known", False) else None
        tcached_out = ar.tokens_cached if getattr(ar, "usage_known", False) else None

        res = _task_result(
            task,
            completed=completed,
            correctness=scoring.r1(correctness),
            unit_tests_passed=passed,
            unit_tests_total=total,
            execution_time_sec=scoring.r1(exec_time),
            tokens_input=tin_out if tin_out is not None else 0,
            tokens_output=tout_out if tout_out is not None else 0,
            tokens_cached=tcached_out if tcached_out is not None else 0,
            cost_usd=cost if cost is not None else 0.0,
            tool_calls=calls,
            unnecessary_steps=ar.unnecessary_steps,
            efficiency_score=scoring.r1(scoring.efficiency_score(ar.unnecessary_steps, exec_time, limit)),
            tool_usage_score=scoring.r1(scoring.tool_usage_score(calls)),
        )
        # Preserve null semantics for UI/analytics (0 above keeps older scorers safe).
        res["tokens_input_reported"] = tin_out
        res["tokens_output_reported"] = tout_out
        res["tokens_cached_reported"] = tcached_out
        res["cost_usd_reported"] = cost
        res["cost_source"] = meta.get("cost_source")
        res["usage_known"] = bool(getattr(ar, "usage_known", False))
        # Stage 2 metrics
        res["model_calls"] = ar.model_calls
        res["successful_tool_calls"] = ar.successful_tool_calls
        res["failed_tool_calls"] = ar.failed_tool_calls
        res["repair_attempts"] = ar.repair_attempts
        res["strategy"] = ar.strategy
        res["error_category"] = ar.error_category
        res["recovered"] = ar.recovered
        if ar.gateway_request_ids:
            res["gateway_request_id"] = ar.gateway_request_ids[0]
            res["gateway_request_ids"] = list(ar.gateway_request_ids)

        if completed:
            res["error"] = None
        else:
            res["error"] = error or ar.error or "Tests failed."
        return res, meta
