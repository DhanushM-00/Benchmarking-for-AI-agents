"""Atlas Coder — genuine ReAct agent (Think → Act → Observe).

System prompts are request-scoped (passed into adapter._call), never a shared global.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from ..adapters import adapter_for, extract_code
from ..tracing import traced_adapter_call
from .base import AgentResult, AgentRunConfig, BaseAgent
from .tools import ToolContext, dispatch_tool, tool_fs_write

ACTION_RE = re.compile(
    r"Action\s*:\s*(?P<tool>[a-z_]+)\s*\nArguments\s*:\s*(?P<args>\{.*?\})?\s*(?:\n|$)",
    re.I | re.S,
)
FINISH_RE = re.compile(r"Action\s*:\s*finish\b", re.I)
THOUGHT_RE = re.compile(r"Thought\s*:\s*(.+?)(?=\nAction\s*:|$)", re.I | re.S)

REACT_SYSTEM = """You are Atlas Coder, a ReAct coding agent.
For every step output EXACTLY this format:

Thought: <brief reasoning>
Action: <tool_name>
Arguments: <single-line JSON object>

Available tools:
- fs_read: {"path": "solution.py"}
- fs_write: {"path": "solution.py", "content": "...full file..."}
- list_dir: {"path": "."}
- grep: {"pattern": "regex", "path": "."}
- shell: {"cmd": "command"}
- python_exec: {"code": "python snippet"}
- pytest: {"path": "smoke_test.py"}
- lint: {"path": "solution.py"}
- finish: {"reason": "done"}

Rules:
- Write the final solution to solution.py via fs_write before finish.
- One Action per response. Do not invent tools.
"""


class AtlasCoderAgent(BaseAgent):
    strategy_name = "react"

    def run(self, task_prompt: str, workspace_dir: str, cfg: AgentRunConfig) -> AgentResult:
        t0 = time.monotonic()
        result = AgentResult(strategy=self.strategy_name)
        adapter = adapter_for(self.agent_doc, self.settings)
        ctx = ToolContext(
            workspace=Path(workspace_dir),
            network_allowed=cfg.network_policy != "none",
        )
        trajectory: list[str] = []
        consecutive_bad = 0
        self._emit(cfg, "agent_started", f"{self.agent_id} ReAct loop started", status="running")

        while (
            result.model_calls < cfg.max_model_calls
            and len(ctx.history) < cfg.max_tool_calls
            and self._deadline_ok(t0, cfg)
        ):
            user = (
                f"Task:\n{task_prompt}\n\n"
                + ("Trajectory so far:\n" + "\n".join(trajectory[-16:]) + "\n\n" if trajectory else "")
                + "Emit the next Thought and Action."
            )
            self._emit(cfg, "model_request_started", "ReAct model step", status="running")
            try:
                text, tin, tout, tcached, meta = traced_adapter_call(
                    adapter,
                    user,
                    temperature=cfg.temperature,
                    max_tokens=cfg.max_tokens_per_call,
                    timeout=self._remaining(t0, cfg),
                    system=REACT_SYSTEM,
                    run_id=cfg.run_id,
                    agent_id=cfg.agent_id or self.agent_id,
                    task_id=cfg.task_id,
                    strategy=self.strategy_name,
                    phase="react_step",
                    attempt=result.model_calls + 1,
                    on_record=getattr(cfg, "on_model_call", None),
                )
            except Exception as e:
                result.error = str(e)[:200]
                result.error_category = "rate_limit" if "429" in str(e) else "model_api"
                result.status = "error"
                self._emit(cfg, "model_response_received", f"error: {result.error}", status="error")
                break

            result.model_calls += 1
            result.add_tokens(tin, tout, tcached)
            if meta.get("request_id"):
                result.gateway_request_ids.append(str(meta["request_id"]))
            result.model_used = meta.get("model") or result.model_used
            result.provider_used = meta.get("provider") or result.provider_used
            if meta.get("cost") is not None:
                result.cost_usd_gateway = (result.cost_usd_gateway or 0) + float(meta["cost"])
            self._emit(
                cfg,
                "model_response_received",
                f"tokens in={tin} out={tout}",
                status="ok",
                gateway_request_id=meta.get("request_id"),
            )

            thought_m = THOUGHT_RE.search(text or "")
            thought = (thought_m.group(1).strip() if thought_m else "")[:300]
            result.steps.append({"phase": "thought", "detail": thought or (text or "")[:200]})

            if FINISH_RE.search(text or ""):
                result.steps.append({"phase": "finish", "detail": "agent requested finish"})
                break

            m = ACTION_RE.search(text or "")
            if not m:
                code = extract_code(text or "")
                if code:
                    self._emit(cfg, "tool_selected", "fs_write (implicit)", status="running")
                    self._emit(cfg, "tool_execution_started", "fs_write solution.py", status="running")
                    tool_fs_write(ctx, "solution.py", code)
                    self._emit(cfg, "tool_execution_completed", "fs_write ok", status="ok")
                    result.steps.append({"phase": "act", "detail": "implicit fs_write from code block"})
                    consecutive_bad = 0
                    trajectory.append("Thought: emit solution\nAction: fs_write\nObservation: wrote solution.py")
                    if result.model_calls >= 2:
                        break
                    continue
                consecutive_bad += 1
                result.unnecessary_steps += 1
                trajectory.append(
                    "Observation: invalid format — respond with Thought/Action/Arguments. "
                    f"Got: {(text or '')[:160]}"
                )
                if consecutive_bad >= 3:
                    result.error_category = "invalid_output"
                    result.error = "Agent failed to follow ReAct format"
                    result.status = "failed"
                    break
                continue

            consecutive_bad = 0
            tool = m.group("tool").strip().lower()
            args_raw = m.group("args") or "{}"
            try:
                args = json.loads(args_raw)
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = {}

            if tool == "finish":
                result.steps.append({"phase": "finish", "detail": str(args.get("reason", "done"))})
                break

            self._emit(cfg, "tool_selected", tool, status="running")
            self._emit(cfg, "tool_execution_started", tool, status="running")
            obs = dispatch_tool(ctx, tool, args)
            outcome = "ok" if not str(obs).startswith("ERROR") else "error"
            self._emit(
                cfg,
                "tool_execution_completed" if outcome == "ok" else "tool_execution_failed",
                f"{tool}: {str(obs)[:160]}",
                status=outcome,
            )
            result.steps.append({"phase": "act", "detail": f"{tool} {args_raw[:80]}"})
            result.steps.append({"phase": "observe", "detail": obs[:200]})
            trajectory.append(
                f"Thought: {thought}\nAction: {tool}\nArguments: {args_raw}\nObservation: {obs[:800]}"
            )

        for call in ctx.history:
            result.record_tool(call)

        sol = ctx.workspace / "solution.py"
        if sol.is_file():
            result.code = sol.read_text(encoding="utf-8", errors="replace")
        elif result.status == "ok":
            result.status = "failed"
            result.error = result.error or "Agent finished without writing solution.py"
            result.error_category = result.error_category or "invalid_output"

        if not self._deadline_ok(t0, cfg) and not result.code:
            result.status = "timeout"
            result.error_category = "timeout"
            result.error = "Time budget exhausted"
        elif result.model_calls >= cfg.max_model_calls and not result.code:
            result.status = "budget_exhausted"
            result.error_category = "budget"
            result.error = result.error or "Model-call budget exhausted"

        status = "ok" if result.status == "ok" and result.code else "error"
        self._emit(cfg, "agent_completed", f"ReAct status={result.status}", status=status)
        result.latency_sec = time.monotonic() - t0
        result.final_output = (result.code or "")[:500]
        return result
