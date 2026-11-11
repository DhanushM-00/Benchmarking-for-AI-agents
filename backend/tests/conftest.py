"""Shared test helpers and fixtures for the Bifrost backend test suite."""
from __future__ import annotations

from app.schemas import FairnessConfig, MetricWeights

# Default fairness payload used by API-level tests. Must satisfy FairnessConfig validation.
CFG = {
    "time_limit_per_task_sec": 30,
    "max_tokens_per_task": 4000,
    "repeats": 1,
    "isolation": "subprocess",
    "container_image": "bifrost/sandbox:py3.11-slim",
    "network_policy": "none",
    "randomize_task_order": False,
    "random_seed": 7,
    "scorer_version": "scorer-2026.03.1",
    "temperature": 0.0,
    "blinded_evaluation": True,
    "metric_weights": {
        "task_success": 0.25,
        "correctness": 0.30,
        "efficiency": 0.15,
        "tool_usage": 0.15,
        "consistency": 0.15,
    },
}


def fairness_config(**overrides) -> FairnessConfig:
    """Return a FairnessConfig, optionally overriding defaults."""
    data = {**CFG, **overrides}
    return FairnessConfig(**data)
