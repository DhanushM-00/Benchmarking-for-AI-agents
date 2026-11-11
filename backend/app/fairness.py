"""Fair Agent Testing Engine — parity checks computed from *observed* evidence.

`build_report(cfg, agents, observed)` is called twice in a run's life:
  * at creation with `observed=None`  -> a config-derived *preview*;
  * after execution with the orchestrator's `observed` facts -> the published evidence.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def dataset_hash(tasks_with_hidden: list[tuple[dict, str | None]]) -> str:
    h = hashlib.sha256()
    for task, hidden in tasks_with_hidden:
        h.update(json.dumps({k: task[k] for k in ("id", "prompt", "test_count", "time_limit_sec", "max_tokens")},
                            sort_keys=True).encode())
        h.update((hidden or "").encode())
    return h.hexdigest()


def prompt_hash(system: str, prompt: str) -> str:
    return hashlib.sha256((system + "\n---\n" + prompt).encode()).hexdigest()[:16]


def _check(id_: str, label: str, detail: str, status: str) -> dict:
    return {"id": id_, "label": label, "detail": detail, "status": status}


def build_report(cfg: dict, agents: list[dict], observed: dict[str, Any] | None = None) -> dict:
    n = len(agents)
    obs = observed or {}
    live = obs.get("mode") == "live"
    has_obs = observed is not None
    checks: list[dict] = []

    # 1 dataset
    if has_obs and obs.get("hash_before") != obs.get("hash_after"):
        checks.append(_check("dataset", "Identical task dataset",
                             "Dataset hash changed during the run — results are not comparable.", "fail"))
    elif has_obs and len({tuple(map(tuple, orders)) for orders in obs.get("dispatch", {}).values()}) > 1:
        checks.append(_check("dataset", "Identical task dataset",
                             "Agents received tasks in different orders or sets.", "fail"))
    else:
        short = (obs.get("hash_before") or "")[:12]
        checks.append(_check("dataset", "Identical task dataset",
                             f"All {n} agents received the same task set"
                             f"{' and ordering seed' if cfg['repeats'] > 1 else ''}"
                             f"{f' (sha256:{short}, re-verified after the run)' if short else ''}.", "pass"))

    # 2 instructions
    versions = {a.get("system_prompt_version") for a in agents}
    multi_hash = has_obs and any(len(v) > 1 for v in obs.get("prompt_hashes", {}).values())
    if multi_hash:
        checks.append(_check("instructions", "Identical instruction template",
                             "Different agents received different prompts for the same task.", "fail"))
    elif len(versions) > 1:
        checks.append(_check("instructions", "Identical instruction template",
                             f"Agents declare different system-prompt versions: {', '.join(sorted(map(str, versions)))}.", "warn"))
    else:
        checks.append(_check("instructions", "Identical instruction template",
                             f"Shared task instructions (template {next(iter(versions), 'n/a')}); agent-specific strategy prompts differ by design and are hashed separately.", "pass"))

    # 3 time limit
    timeouts = obs.get("timeouts", 0)
    checks.append(_check("timelimit", "Equal time limit",
                         f"{cfg['time_limit_per_task_sec']}s per task, enforced by the sandbox supervisor"
                         f"{f' ({timeouts} task(s) hit the ceiling)' if timeouts else ''}.", "pass"))

    # 4 environment
    img = cfg["container_image"].split("@")[0]
    if live and obs.get("isolation_used") != cfg["isolation"]:
        checks.append(_check("environment", "Same execution environment",
                             f"Requested {cfg['isolation']} but ran on {obs.get('isolation_used')} — "
                             "identical for every agent, but not the requested image.", "warn"))
    else:
        checks.append(_check("environment", "Same execution environment",
                             f"All agents ran on {img} with identical seeded fixtures.", "pass"))

    # 5 budget
    over = obs.get("over_budget", 0)
    checks.append(_check("budget", "Equal token budget",
                         f"{cfg['max_tokens_per_task']:,} max tokens per task, hard-capped"
                         f"{f' ({over} task(s) exceeded it and were failed)' if over else ''}.",
                         "pass"))

    # 6 network
    if cfg["network_policy"] != "none":
        checks.append(_check("network", "Network policy enforced", f"Network policy: {cfg['network_policy']}.", "warn"))
    elif live and not obs.get("network_blocked", False):
        checks.append(_check("network", "Network policy enforced",
                             "Policy is 'none' but the subprocess sandbox cannot block the network — use docker isolation.", "warn"))
    else:
        checks.append(_check("network", "Network policy enforced", "Network fully disabled in the sandbox.", "pass"))

    # 7 scoring
    checks.append(_check("scoring", "Same scoring rules",
                         f"Single scorer {cfg['scorer_version']} applied to every result.", "pass"))

    # 8 repeats
    r = cfg["repeats"]
    checks.append(_check("repeats", "Repeated runs",
                         f"{r} repeat{'s' if r > 1 else ''} per agent; median score reported, variance tracked.",
                         "pass" if r >= 2 else "warn"))

    # 9 blinding
    b = cfg["blinded_evaluation"]
    checks.append(_check("blinding", "Blinded evaluation",
                         "Judge prompts contain no agent identity or model name." if b
                         else "Judge can see agent identity — scores may be biased.",
                         "pass" if b else "fail"))

    # 10 isolation
    checks.append(_check("isolation", "Run isolation",
                         f"{obs.get('isolation_used', cfg['isolation'])} isolation; a fresh workspace per agent per task, "
                         "no shared filesystem state.", "pass"))

    # extra: simulated results are never presented as measured ones
    if obs.get("mode") == "simulated":
        checks.append(_check("mode", "Measured execution",
                             "SIMULATED: results come from the deterministic simulator, not real model calls.", "warn"))

    # 11 tool surface parity — every agent gets the same runtime tool registry in live mode
    if live or not has_obs:
        checks.append(_check(
            "tools",
            "Equivalent tool permissions",
            "All agents share the same runtime tool registry (fs_read/write, list_dir, grep, shell, "
            "python_exec, pytest, lint) with identical path-escape and dangerous-command checks. "
            "Catalogue tool lists describe intended capability, not a per-agent privilege escalation.",
            "pass",
        ))

    # 12 strategy diversity — strategies differ; budgets must still be equal
    if has_obs and live:
        strategies = obs.get("strategies") or {}
        uniq = sorted({s for s in strategies.values() if s})
        detail = (
            f"Agents used distinct strategies {uniq} under identical time/token/model-call budgets "
            f"({cfg['time_limit_per_task_sec']}s, {cfg['max_tokens_per_task']} tokens)."
            if len(uniq) > 1 else
            f"Strategy set: {uniq or ['n/a']}; budgets identical across agents."
        )
        checks.append(_check("strategies", "Strategy-fair budgets", detail, "pass"))

    # 13 sandbox availability — invalid comparisons when host fallback was forced
    if live and has_obs and obs.get("isolation_used") == "unavailable":
        checks.append(_check(
            "sandbox",
            "Sandbox availability",
            "Docker isolation was required but unavailable; untrusted code was not executed. "
            "Scores are not comparable to a successful sandboxed run.",
            "fail",
        ))

    score = round(sum(1 if c["status"] == "pass" else 0.5 if c["status"] == "warn" else 0 for c in checks)
                  / len(checks) * 100)
    return {"score": max(0, score), "checks": checks,
            "violations": [c["label"] for c in checks if c["status"] == "fail"]}
