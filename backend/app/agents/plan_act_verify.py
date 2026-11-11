"""Nova Coder — Plan → Act → Verify (with budgeted repair).

System prompts are request-scoped via adapter._call(..., system=...), never a shared global.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..adapters import adapter_for, extract_code
from ..tracing import traced_adapter_call
from .base import AgentResult, AgentRunConfig, BaseAgent
from .tools import ToolContext, tool_fs_write, tool_lint, tool_python_exec

PLAN_SYSTEM = """You are Nova Coder in PLAN phase.
Produce a numbered plan (3-7 steps) to implement the task in solution.py.
Do not write code yet. Output only the plan."""

ACT_SYSTEM = """You are Nova Coder in ACT phase.
Implement the full solution in one fenced ```python code block for solution.py.
Follow the plan. No explanations outside the code block."""

REPAIR_SYSTEM = """You are Nova Coder in REPAIR phase.
The previous solution failed verification. Output a corrected full ```python code block for solution.py.
Address the failure notes. No explanations outside the code block."""


class NovaCoderAgent(BaseAgent):
    strategy_name = "plan_act_verify"

    def run(self, task_prompt: str, workspace_dir: str, cfg: AgentRunConfig) -> AgentResult:
        t0 = time.monotonic()
        result = AgentResult(strategy=self.strategy_name)
        adapter = adapter_for(self.agent_doc, self.settings)
        ctx = ToolContext(workspace=Path(workspace_dir), network_allowed=cfg.network_policy != "none")
        plan_text = ""
        self._emit(cfg, "agent_started", f"{self.agent_id} Plan-Act-Verify started", status="running")

        def _call(system: str, user: str, phase: str = "pav") -> tuple[str, dict]:
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
            return text or "", meta

        # PLAN
        if not self._deadline_ok(t0, cfg):
            result.status = "timeout"
            result.error_category = "timeout"
            result.error = "Timed out before plan"
            result.latency_sec = time.monotonic() - t0
            return result
        try:
            self._emit(cfg, "model_request_started", "PLAN phase", status="running")
            plan_text, _ = _call(PLAN_SYSTEM, f"Task:\n{task_prompt}\n\nWrite the plan.", phase="plan")
            result.steps.append({"phase": "plan", "detail": plan_text[:400]})
            self._emit(cfg, "planning_completed", "plan ready", status="ok")
        except Exception as e:
            result.error = str(e)[:200]
            result.error_category = "model_api"
            result.status = "error"
            result.latency_sec = time.monotonic() - t0
            self._emit(cfg, "agent_completed", result.error, status="error")
            return result

        # ACT
        if result.model_calls >= cfg.max_model_calls or not self._deadline_ok(t0, cfg):
            result.status = "budget_exhausted"
            result.error_category = "budget"
            result.error = "Budget exhausted before act"
        else:
            try:
                self._emit(cfg, "model_request_started", "ACT phase", status="running")
                act_text, _ = _call(
                    ACT_SYSTEM,
                    f"Task:\n{task_prompt}\n\nPlan:\n{plan_text}\n\nImplement solution.py now.",
                    phase="act",
                )
                code = extract_code(act_text)
                if code:
                    tool_fs_write(ctx, "solution.py", code)
                    result.code = code
                    result.steps.append({"phase": "act", "detail": f"wrote solution.py ({len(code)} chars)"})
                    self._emit(cfg, "tool_execution_completed", "fs_write solution.py", status="ok")
                else:
                    result.unnecessary_steps += 1
                    result.steps.append({"phase": "act", "detail": "no code block in act response"})
            except Exception as e:
                result.error = str(e)[:200]
                result.error_category = "model_api"
                result.status = "error"

        # VERIFY + REPAIR
        repairs = 0
        while (
            result.status not in ("error", "timeout")
            and repairs <= cfg.max_repair_attempts
            and self._deadline_ok(t0, cfg)
            and result.model_calls < cfg.max_model_calls
        ):
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
            result.steps.append({"phase": "verify", "detail": f"lint={lint_out[:120]}; import={import_out[:120]}"})
            lint_ok = lint_out.startswith("OK")
            import_ok = "import_ok" in import_out and not import_out.startswith("ERROR")
            self._emit(
                cfg,
                "verification_completed",
                f"lint_ok={lint_ok} import_ok={import_ok}",
                status="ok" if lint_ok and import_ok else "error",
            )

            if lint_ok and import_ok and result.code:
                result.recovered = repairs > 0
                break

            if repairs >= cfg.max_repair_attempts:
                result.error_category = result.error_category or "incorrect"
                if not result.code:
                    result.status = "failed"
                    result.error = result.error or "Verify failed and no solution produced"
                break

            repairs += 1
            result.repair_attempts = repairs
            self._emit(cfg, "retry_started", f"repair #{repairs}", status="running")
            notes = f"Lint: {lint_out}\nImport: {import_out}"
            try:
                repair_text, _ = _call(
                    REPAIR_SYSTEM,
                    f"Task:\n{task_prompt}\n\nPlan:\n{plan_text}\n\nFailure notes:\n{notes}\n\n"
                    f"Current solution:\n{result.code or '(empty)'}",
                    phase="repair",
                )
                code = extract_code(repair_text)
                if code:
                    tool_fs_write(ctx, "solution.py", code)
                    result.code = code
                    result.steps.append({"phase": "repair", "detail": f"repair #{repairs}"})
                else:
                    result.unnecessary_steps += 1
                    result.steps.append({"phase": "repair", "detail": f"repair #{repairs} produced no code"})
            except Exception as e:
                result.error = str(e)[:200]
                result.error_category = "model_api"
                result.status = "error"
                break

        for call in ctx.history:
            result.record_tool(call)

        if not result.code and result.status == "ok":
            result.status = "failed"
            result.error = result.error or "No solution.py produced"
            result.error_category = result.error_category or "invalid_output"

        if not self._deadline_ok(t0, cfg) and result.status == "ok" and not result.code:
            result.status = "timeout"
            result.error_category = "timeout"

        self._emit(cfg, "agent_completed", f"PAV status={result.status}", status="ok" if result.code else "error")
        result.latency_sec = time.monotonic() - t0
        result.final_output = (result.code or "")[:500]
        return result
