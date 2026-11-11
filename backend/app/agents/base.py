"""Framework-independent agent interface.

Every strategy implements the same contract so the orchestrator and scoring layer
do not care whether the agent is ReAct, Plan-Act-Verify, or a state machine.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRunConfig:
    """Per-task budget and parity controls — identical for every agent in a run."""
    temperature: float = 0.2
    max_tokens_per_call: int = 2048
    time_limit_sec: float = 120.0
    max_model_calls: int = 12
    max_tool_calls: int = 40
    max_repair_attempts: int = 3
    isolation: str = "subprocess"
    network_policy: str = "none"
    # Optional structured event sink: callable(type, message, **fields) — set by LiveExecutor
    on_event: Any | None = None
    on_model_call: Any | None = None
    agent_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None


@dataclass
class AgentResult:
    """Uniform result every agent must produce."""
    code: str | None = None
    status: str = "ok"  # ok | failed | timeout | budget_exhausted | error
    error: str | None = None
    error_category: str | None = None  # model_api | rate_limit | tool | invalid_output | sandbox | timeout | budget | loop | incorrect
    recovered: bool = False

    # Accounting — tokens stay 0 until a call reports usage; usage_known distinguishes
    # "gateway omitted usage" from "zero tokens billed".
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cached: int = 0
    usage_known: bool = False
    cost_usd_gateway: float | None = None
    latency_sec: float = 0.0
    model_calls: int = 0
    tool_calls: list[dict] = field(default_factory=list)
    successful_tool_calls: int = 0
    failed_tool_calls: int = 0
    repair_attempts: int = 0
    unnecessary_steps: int = 0

    # Observability (Stage 1 gateway + Stage 2 strategy)
    gateway_request_ids: list[str] = field(default_factory=list)
    model_used: str | None = None
    provider_used: str | None = None
    strategy: str = ""
    steps: list[dict] = field(default_factory=list)  # high-level strategy steps for UI/debug
    final_output: str | None = None

    def add_tokens(self, tin: int | None, tout: int | None, tcached: int | None = None) -> None:
        # Only add counts the gateway actually reported. None is not zero.
        if tin is not None:
            self.tokens_input += int(tin)
            self.usage_known = True
        if tout is not None:
            self.tokens_output += int(tout)
            self.usage_known = True
        if tcached is not None:
            self.tokens_cached += int(tcached)
            self.usage_known = True

    def record_tool(self, call: dict) -> None:
        self.tool_calls.append(call)
        if call.get("outcome") == "success":
            self.successful_tool_calls += 1
        else:
            self.failed_tool_calls += 1


class BaseAgent(ABC):
    """Common interface. Subclasses implement `run` with different control flows."""

    strategy_name: str = "base"

    def __init__(self, agent_doc: dict, settings: Any):
        self.agent_doc = agent_doc
        self.settings = settings
        self.agent_id = agent_doc.get("id", "unknown")

    @abstractmethod
    def run(self, task_prompt: str, workspace_dir: str, cfg: AgentRunConfig) -> AgentResult:
        """Execute the task. Must not read hidden tests. Write solution to workspace/solution.py."""

    def _deadline_ok(self, t0: float, cfg: AgentRunConfig) -> bool:
        return (time.monotonic() - t0) < cfg.time_limit_sec

    def _remaining(self, t0: float, cfg: AgentRunConfig) -> float:
        return max(0.5, cfg.time_limit_sec - (time.monotonic() - t0))

    def _emit(self, cfg: AgentRunConfig, type_: str, message: str, **fields) -> None:
        """Emit a structured run event if a sink is configured. Never raises."""
        sink = cfg.on_event
        if not sink:
            return
        try:
            sink(
                type_,
                message,
                agent_id=fields.pop("agent_id", cfg.agent_id or self.agent_id),
                task_id=fields.pop("task_id", cfg.task_id),
                **fields,
            )
        except Exception:
            pass
