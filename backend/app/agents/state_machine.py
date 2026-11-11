"""Forge Coder — explicit state-machine agent (LangGraph-style).

States (edges are data-dependent, not a single prompt):
  PLAN → CODE → TEST → (REPAIR → TEST)* → FINISH | STOP

This is a real control-flow graph implemented in Python. Nodes invoke the model
or tools; transitions depend on test/lint outcomes and remaining budget.
(Equivalent structure to a LangGraph StateGraph without requiring the package
at import time; if langgraph is installed it is not required for correctness.)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..adapters import adapter_for, extract_code
from ..tracing import traced_adapter_call
from .base import AgentResult, AgentRunConfig, BaseAgent
from .tools import ToolContext, tool_fs_write, tool_lint, tool_python_exec

State = Literal["PLAN", "CODE", "TEST", "REPAIR", "FINISH", "STOP"]


@dataclass
class GraphState:
    task: str
    plan: str = ""
    code: str = ""
    test_notes: str = ""
    repair_count: int = 0
    status: State = "PLAN"
    history: list[str] = field(default_factory=list)


PLAN_SYS = "You are Forge Coder (PLAN node). Output a short numbered implementation plan only."
CODE_SYS = (
    "You are Forge Coder (CODE node). Output one complete ```python code block for solution.py. "
    "No prose outside the fence."
)
REPAIR_SYS = (
    "You are Forge Coder (REPAIR node). Fix solution.py. Output one complete ```python code block. "
    "Address the test notes."
)


class ForgeCoderAgent(BaseAgent):
    strategy_name = "state_machine"

    def run(self, task_prompt: str, workspace_dir: str, cfg: AgentRunConfig) -> AgentResult:
        
        t0 = time.monotonic()
        result = AgentResult(strategy=self.strategy_name)
        adapter = adapter_for(self.agent_doc, self.settings)
        ctx = ToolContext(workspace=Path(workspace_dir), network_allowed=cfg.network_policy != "none")
        g = GraphState(task=task_prompt)
        self._emit(cfg, "agent_started", f"{self.agent_id} state-machine started", status="running")

        def model_node(system: str, user: str, phase: str = "sm") -> str:
            text, tin, tout, tcached, meta = traced_adapter_call(
                adapter,
                user,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens_per_call,
                timeout=self._remaining(t0, cfg),
                system=system,
                run_id=cfg.run_id,
                agent_id=cfg.agent_id or self.agent_id,
                task_id=cfg.task_id,
                strategy=self.strategy_name,
                phase=phase,
                attempt=result.model_calls + 1,
                is_retry=phase == "repair",
                on_record=getattr(cfg, "on_model_call", None),
            )
            result.model_calls += 1
            result.add_tokens(tin, tout, tcached)
            if meta.get("request_id"):
                result.gateway_request_ids.append(str(meta["request_id"]))
            result.model_used = meta.get("model") or result.model_used
            result.provider_used = meta.get("provider") or result.provider_used
            if meta.get("cost") is not None:
                result.cost_usd_gateway = (result.cost_usd_gateway or 0) + float(meta["cost"])
            return text or ""


        steps_guard = 0
        while g.status not in ("FINISH", "STOP") and steps_guard < 20:
            steps_guard += 1
            if not self._deadline_ok(t0, cfg):
                g.status = "STOP"
                result.status = "timeout"
                result.error_category = "timeout"
                result.error = "Time budget exhausted in state machine"
                break
            if result.model_calls >= cfg.max_model_calls and g.status in ("PLAN", "CODE", "REPAIR"):
                g.status = "STOP"
                result.status = "budget_exhausted"
                result.error_category = "budget"
                result.error = "Model-call budget exhausted"
                break

            if g.status == "PLAN":
                try:
                    g.plan = model_node(PLAN_SYS, f"Task:\n{g.task}\n\nPlan the implementation.", phase="plan")
                    result.steps.append({"phase": "plan", "detail": g.plan[:300]})
                    self._emit(cfg, "planning_completed", "PLAN done", status="ok")
                    g.history.append("PLAN→CODE")
                    g.status = "CODE"
                except Exception as e:
                    result.error = str(e)[:200]
                    result.error_category = "model_api"
                    result.status = "error"
                    g.status = "STOP"

            elif g.status == "CODE":
                try:
                    text = model_node(
                        CODE_SYS,
                        f"Task:\n{g.task}\n\nPlan:\n{g.plan}\n\nWrite solution.py.",
                    )
                    code = extract_code(text)
                    if code:
                        tool_fs_write(ctx, "solution.py", code)
                        g.code = code
                        result.code = code
                        result.steps.append({"phase": "code", "detail": f"{len(code)} chars"})
                        g.history.append("CODE→TEST")
                        g.status = "TEST"
                    else:
                        result.unnecessary_steps += 1
                        result.steps.append({"phase": "code", "detail": "no code block"})
                        # retry once via REPAIR path budget
                        g.test_notes = "CODE node produced no code block"
                        g.history.append("CODE→REPAIR")
                        g.status = "REPAIR"
                except Exception as e:
                    result.error = str(e)[:200]
                    result.error_category = "model_api"
                    result.status = "error"
                    g.status = "STOP"

            elif g.status == "TEST":
                lint_out = tool_lint(ctx, "solution.py")
                import_out = tool_python_exec(
                    ctx,
                    "import importlib.util\n"
                    "spec=importlib.util.spec_from_file_location('solution','solution.py')\n"
                    "m=importlib.util.module_from_spec(spec)\n"
                    "spec.loader.exec_module(m)\n"
                    "print('import_ok')\n",
                    timeout_sec=8.0,
                )
                g.test_notes = f"lint={lint_out}\nimport={import_out}"
                result.steps.append({"phase": "test", "detail": g.test_notes[:200]})
                lint_ok = lint_out.startswith("OK")
                import_ok = "import_ok" in import_out and not import_out.startswith("ERROR")
                if lint_ok and import_ok and g.code:
                    result.recovered = g.repair_count > 0
                    g.history.append("TEST→FINISH")
                    g.status = "FINISH"
                elif g.repair_count >= cfg.max_repair_attempts:
                    g.history.append("TEST→STOP")
                    g.status = "STOP"
                    if not result.code:
                        result.status = "failed"
                        result.error = "Tests failed after max repairs"
                        result.error_category = "incorrect"
                else:
                    g.history.append("TEST→REPAIR")
                    g.status = "REPAIR"

            elif g.status == "REPAIR":
                g.repair_count += 1
                result.repair_attempts = g.repair_count
                try:
                    text = model_node(
                        REPAIR_SYS,
                        f"Task:\n{g.task}\n\nPlan:\n{g.plan}\n\nNotes:\n{g.test_notes}\n\n"
                        f"Current code:\n{g.code or '(empty)'}",
                    )
                    code = extract_code(text)
                    if code:
                        tool_fs_write(ctx, "solution.py", code)
                        g.code = code
                        result.code = code
                        result.steps.append({"phase": "repair", "detail": f"repair #{g.repair_count}"})
                        g.history.append("REPAIR→TEST")
                        g.status = "TEST"
                    else:
                        result.unnecessary_steps += 1
                        result.steps.append({"phase": "repair", "detail": "no code"})
                        if g.repair_count >= cfg.max_repair_attempts:
                            g.status = "STOP"
                        else:
                            g.status = "TEST"
                except Exception as e:
                    result.error = str(e)[:200]
                    result.error_category = "model_api"
                    result.status = "error"
                    g.status = "STOP"
        for call in ctx.history:
            result.record_tool(call)

        # Persist transition log for failure analysis / UI
        result.steps.append({"phase": "graph", "detail": " → ".join(g.history)})

        if g.status == "FINISH" and result.code:
            result.status = "ok"
        elif result.status == "ok" and not result.code:
            result.status = "failed"
            result.error = result.error or "State machine stopped without solution"
            result.error_category = result.error_category or "invalid_output"

        self._emit(cfg, "agent_completed", f"SM status={result.status} graph={g.status}", status="ok" if result.code else "error")
        result.latency_sec = time.monotonic() - t0
        result.final_output = (result.code or "")[:500]
        return result
