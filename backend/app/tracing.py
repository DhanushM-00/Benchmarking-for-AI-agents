"""Model-call tracing for Bifrost-backed agent runs.

Every live LLM request can be recorded as a structured model_call row linked to
run / agent / task. Values that are unknown stay null — never invented zeros for cost.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class ModelCallContext:
    """Thread-safe identity for concurrent agent workers."""
    run_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    strategy: str | None = None
    on_record: Callable[[dict], None] | None = None
    _local: threading.local = field(default_factory=threading.local, repr=False)

    def bind(self) -> None:
        self._local.ctx = self

    @classmethod
    def current(cls) -> "ModelCallContext | None":
        # best-effort: not used as primary path
        return None


def new_call_id() -> str:
    return f"mc_{uuid.uuid4().hex[:16]}"


def record_model_call(
    *,
    run_id: str | None,
    agent_id: str | None,
    task_id: str | None,
    strategy: str | None,
    provider: str | None,
    model: str | None,
    started_at: str,
    finished_at: str,
    latency_ms: float | None,
    tokens_input: int | None,
    tokens_output: int | None,
    tokens_cached: int | None,
    total_tokens: int | None,
    cost_usd: float | None,
    cost_source: str | None,  # "gateway" | "estimated" | None
    http_status: int | None,
    success: bool,
    error: str | None,
    gateway_request_id: str | None,
    attempt: int = 1,
    is_retry: bool = False,
    streaming: bool | None = None,
    fallback: str | None = None,
    phase: str | None = None,
    meta: dict | None = None,
) -> dict:
    """Build a model-call document. Unknown numerics stay None (not 0)."""
    doc = {
        "id": new_call_id(),
        "run_id": run_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "strategy": strategy,
        "provider": provider,
        "model": model,
        "started_at": started_at,
        "finished_at": finished_at,
        "latency_ms": latency_ms,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "tokens_cached": tokens_cached,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "cost_source": cost_source,
        "http_status": http_status,
        "success": success,
        "error": error,
        "gateway_request_id": gateway_request_id,
        "attempt": attempt,
        "is_retry": is_retry,
        "streaming": streaming,
        "fallback": fallback,
        "phase": phase,
        "metadata": meta or {},
    }
    return doc


def traced_adapter_call(
    adapter: Any,
    prompt: str,
    *,
    temperature: float,
    max_tokens: int,
    timeout: float,
    system: str | None,
    run_id: str | None,
    agent_id: str | None,
    task_id: str | None,
    strategy: str | None,
    phase: str | None = None,
    attempt: int = 1,
    is_retry: bool = False,
    on_record: Callable[[dict], None] | None = None,
) -> tuple[str, int, int, int, dict]:
    """Wrap adapter._call and persist a model_call record (success or failure)."""
    started = _now()
    t0 = time.monotonic()
    text, tin, tout, tcached, meta = "", 0, 0, 0, {}
    err = None
    success = False
    try:
        text, tin, tout, tcached, meta = adapter._call(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            system=system,
        )
        success = True
        return text, tin, tout, tcached, meta
    except Exception as e:
        err = str(e)[:400]
        meta = dict(getattr(e, "meta", None) or {})
        if getattr(e, "request_id", None):
            meta.setdefault("request_id", e.request_id)
        if getattr(e, "status_code", None) is not None:
            meta.setdefault("status_code", e.status_code)
        if getattr(e, "provider", None):
            meta.setdefault("provider", e.provider)
        if getattr(e, "model", None):
            meta.setdefault("model", e.model)
        if getattr(e, "error_type", None):
            meta.setdefault("error_type", e.error_type)
        raise
    finally:
        finished = _now()
        latency_ms = round((time.monotonic() - t0) * 1000, 2)

        def _tok(v: Any) -> int | None:
            if v is None or isinstance(v, bool):
                return None
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        # Missing usage stays null. Explicit 0 is preserved. Do not sum a partial pair.
        if success:
            ti = _tok(tin)
            to = _tok(tout)
            tc = _tok(tcached)
            total = (ti + to) if ti is not None and to is not None else None
        else:
            ti = to = tc = total = None
        cost = None
        cost_source = None
        if success and meta.get("cost") is not None:
            try:
                cost = float(meta["cost"])
                cost_source = "gateway"
            except (TypeError, ValueError):
                cost = None
        http_status = meta.get("status_code")
        if isinstance(http_status, str) and http_status.isdigit():
            http_status = int(http_status)
        doc = record_model_call(
            run_id=run_id,
            agent_id=agent_id,
            task_id=task_id,
            strategy=strategy,
            provider=meta.get("provider") or getattr(adapter, "provider", None) or None,
            model=meta.get("model") or getattr(adapter, "model", None),
            started_at=started,
            finished_at=finished,
            latency_ms=latency_ms,
            tokens_input=ti,
            tokens_output=to,
            tokens_cached=tc,
            total_tokens=total,
            cost_usd=cost,
            cost_source=cost_source,
            http_status=http_status,
            success=success,
            error=err,
            gateway_request_id=meta.get("request_id"),
            attempt=attempt,
            is_retry=is_retry,
            streaming=False,
            fallback=meta.get("fallback"),
            phase=phase,
            meta={
                "source": meta.get("source"),
                "gateway_url": getattr(adapter, "gateway_url", None),
            },
        )
        if on_record:
            try:
                on_record(doc)
            except Exception:
                pass
