"""Model adapters. Every agent gets the *same* system prompt and the *same* task prompt; only the
model/provider differs. An adapter turns (prompt) into code + a token ledger.

All live model traffic goes through the Maxim AI Bifrost gateway (OpenAI-compatible).
Direct Gemini / OpenRouter HTTP calls are removed from the normal execution path.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

def _optional_int(value: Any) -> int | None:
    """Parse an explicit integer. None stays None (missing is not zero)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_gateway_cost(usage: dict | None) -> float | None:
    """Extract the request cost in USD from a usage block (number or Bifrost cost object)."""
    if not isinstance(usage, dict):
        return None
    raw = usage.get("cost")
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float, str)):
        try:
            return float(raw)
        except ValueError:
            return None
    if isinstance(raw, dict):
        if raw.get("total_cost") is not None:
            try:
                return float(raw["total_cost"])
            except (TypeError, ValueError):
                return None
        parts = [
            raw.get(k)
            for k in (
                "input_tokens_cost", "output_tokens_cost", "reasoning_tokens_cost",
                "citation_tokens_cost", "search_queries_cost", "request_cost",
            )
            if isinstance(raw.get(k), (int, float))
        ]
        return float(sum(parts)) if parts else None
    return None


def parse_openai_usage(usage: dict | None) -> tuple[int | None, int | None, int | None]:
    """Return (input, output, cached) tokens.

    A key that is absent is None. An explicit 0 stays 0.
    """
    if not isinstance(usage, dict) or not usage:
        return None, None, None
    if "prompt_tokens" in usage:
        tin = _optional_int(usage.get("prompt_tokens"))
    elif "input_tokens" in usage:
        tin = _optional_int(usage.get("input_tokens"))
    else:
        tin = None
    if "completion_tokens" in usage:
        tout = _optional_int(usage.get("completion_tokens"))
    elif "output_tokens" in usage:
        tout = _optional_int(usage.get("output_tokens"))
    else:
        tout = None
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    if isinstance(details, dict) and "cached_tokens" in details:
        tcached = _optional_int(details.get("cached_tokens"))
    elif "cached_tokens" in usage:
        tcached = _optional_int(usage.get("cached_tokens"))
    else:
        tcached = None
    return tin, tout, tcached


SYSTEM_PROMPT = (
    "You are a coding agent in a benchmark. Reply with exactly ONE fenced ```python code block containing the "
    "complete contents of `solution.py`. Do not include explanations, example usage or tests."
)


@dataclass
class Generation:
    code: str | None
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cached: int = 0
    latency_sec: float = 0.0
    tool_calls: list[dict] = field(default_factory=list)
    unnecessary_steps: int = 0
    error: str | None = None
    # Gateway / observability metadata (Stage 1)
    gateway_request_id: str | None = None
    model_used: str | None = None
    provider_used: str | None = None
    cost_usd_gateway: float | None = None  # when Bifrost reports cost
    source: str = "bifrost"  # "bifrost" | "direct" (direct only if explicitly disabled)


class ModelError(RuntimeError):
    """Gateway/model failure that preserves observability metadata."""

    def __init__(
        self,
        message: str,
        *,
        request_id: str | None = None,
        status_code: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        error_type: str | None = None,
        latency_ms: float | None = None,
        meta: dict | None = None,
    ):
        super().__init__(message)
        self.request_id = request_id
        self.status_code = status_code
        self.provider = provider
        self.model = model
        self.error_type = error_type or "model_error"
        self.latency_ms = latency_ms
        self.meta = meta or {}


_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S | re.I)


def extract_code(text: str) -> str | None:
    m = _FENCE.search(text or "")
    return m.group(1).strip() + "\n" if m else None


def bifrost_model_id(agent: dict) -> str:
    """Map catalogue agent → Bifrost model identifier (provider/model).

    Bifrost expects provider-prefixed model names, e.g.:
      - gemini/gemini-2.5-pro
      - openrouter/google/gemini-2.5-pro
      - openai/gpt-4o-mini
    """
    provider = (agent.get("model_provider") or "").strip().lower()
    model = (agent.get("model") or "").strip()
    if not model:
        raise ModelError("agent has empty model")

    # Already prefixed?
    if "/" in model and not model.startswith("google/"):
        # openrouter-style or already bifrost-style
        if provider in ("openrouter",) and not model.startswith("openrouter/"):
            return f"openrouter/{model}"
        return model

    if provider in ("google ai", "google", "gemini"):
        # Native Gemini provider in Bifrost
        return f"gemini/{model}"
    if provider == "openrouter":
        # Prefer routing via OpenRouter provider; many models are google/...
        if model.startswith("google/") or model.startswith("openai/") or model.startswith("anthropic/"):
            return f"openrouter/{model}"
        return f"openrouter/google/{model}"
    # Fallback: treat as openai-compatible bare name
    return f"openai/{model}" if "/" not in model else model


class Adapter:
    provider = ""

    def __init__(self, api_key: str, model: str, **kwargs: Any):
        self.api_key = api_key
        self.model = model
        self.extra = kwargs

    def _call(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
        system: str | None = None,
    ) -> tuple[str, int, int, int, dict]:
        """Return (text, tokens_in, tokens_out, tokens_cached, meta).

        `system` is request-scoped — never mutate module-level SYSTEM_PROMPT.
        """
        raise NotImplementedError

    def solve(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
        system: str | None = None,
    ) -> Generation:
        gen = Generation(code=None)
        t0 = time.monotonic()
        for attempt in range(2):  # one retry if the reply has no extractable code block
            remaining = timeout - (time.monotonic() - t0)
            if remaining <= 1:
                gen.error = "Sandbox timeout — agent did not finish within the limit."
                break
            try:
                text, tin, tout, tcached, meta = self._call(
                    prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=remaining,
                    system=system,
                )
            except (httpx.HTTPError, ModelError, OSError) as e:
                gen.error = f"Model API error: {str(e)[:180]}"
                gen.tool_calls.append({
                    "tool": "model_call",
                    "args_summary": f"attempt={attempt + 1}",
                    "outcome": "error",
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                })
                break
            # Preserve missing usage as-is; do not treat absent gateway usage as zero.
            if tin is not None:
                gen.tokens_input += int(tin)
            if tout is not None:
                gen.tokens_output += int(tout)
            if tcached is not None:
                gen.tokens_cached += int(tcached)
            if meta:
                gen.gateway_request_id = meta.get("request_id") or gen.gateway_request_id
                gen.model_used = meta.get("model") or gen.model_used
                gen.provider_used = meta.get("provider") or gen.provider_used
                if meta.get("cost") is not None:
                    gen.cost_usd_gateway = float(meta["cost"])
                gen.source = meta.get("source", gen.source)
            gen.code = extract_code(text)
            if gen.code:
                gen.tool_calls.append({
                    "tool": "fs_write",
                    "args_summary": "path=solution.py",
                    "outcome": "success",
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                })
                break
            gen.unnecessary_steps += 1
            gen.tool_calls.append({
                "tool": "fs_write",
                "args_summary": "path=solution.py (no code block)",
                "outcome": "rejected",
                "duration_ms": round((time.monotonic() - t0) * 1000),
            })
            if gen.tokens_output >= max_tokens:
                break
        if gen.code is None and gen.error is None:
            gen.error = "Agent returned no code block."
        gen.latency_sec = time.monotonic() - t0
        return gen


def bifrost_auth_headers(api_key: str | None) -> dict[str, str]:
    """Auth headers for the Bifrost gateway.

    Bifrost v2 (>= 2.0) expects the **virtual key** in the ``x-bf-vk``
    header — it answers ``401 virtual key is required. Provide a virtual key
    via the x-bf-vk header.`` when the key is missing or sent only as an
    ``Authorization`` header.

    ``Authorization: Bearer`` is sent as well so the platform keeps working
    with OpenAI-compatible gateways that follow the standard header.

    No key means no auth header at all: sending a placeholder would be
    reported by Bifrost as "invalid virtual key", which is misleading.
    """
    key = (api_key or "").strip()
    if not key:
        return {}
    return {"x-bf-vk": key, "Authorization": f"Bearer {key}"}


class BifrostAdapter(Adapter):
    """All live traffic goes through Maxim AI Bifrost (OpenAI-compatible gateway).

    Capabilities used:
    - Model routing via provider/model identifiers
    - Automatic fallback (configured inside Bifrost)
    - Request timeout
    - Token usage from response.usage
    - Cost when Bifrost returns it
    - Request identifiers (x-request-id / response id / headers)
    """
    provider = "Bifrost"

    def __init__(self, gateway_url: str, api_key: str, model: str, agent_provider: str = "", **kwargs: Any):
        super().__init__(api_key, model, **kwargs)
        self.gateway_url = gateway_url.rstrip("/")
        self.agent_provider = agent_provider
        # Resolve chat completions endpoint
        if self.gateway_url.endswith("/v1/chat/completions"):
            self.chat_url = self.gateway_url
        else:
            self.chat_url = f"{self.gateway_url}/v1/chat/completions"

    def _call(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
        system: str | None = None,
    ) -> tuple[str, int, int, int, dict]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "bifrost-benchmark-platform/1.0",
        }
        # Bifrost v2 wants the virtual key in x-bf-vk (see bifrost_auth_headers).
        headers.update(bifrost_auth_headers(self.api_key))

        sys_content = system if system is not None else SYSTEM_PROMPT
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": prompt},
            ],
        }

        try:
            r = httpx.post(self.chat_url, headers=headers, json=payload, timeout=timeout)
        except httpx.TimeoutException as e:
            raise ModelError(f"Bifrost gateway timeout after {timeout:.0f}s: {e}") from e
        except httpx.ConnectError as e:
            raise ModelError(
                f"Bifrost gateway unavailable at {self.gateway_url}: {e}. "
                "Start it with: npx -y @maximhq/bifrost -port 8081  (or run scripts\\start-bifrost.ps1). Port 8080 is often already taken."
            ) from e
        except httpx.HTTPError as e:
            raise ModelError(f"Bifrost transport error: {e}") from e

        # Capture request id from common header names
        req_id = (
            r.headers.get("x-request-id")
            or r.headers.get("x-bifrost-request-id")
            or r.headers.get("cf-ray")
            or r.headers.get("x-requestid")
        )

        if r.status_code == 401 or r.status_code == 403:
            raise ModelError(f"Bifrost auth failed (HTTP {r.status_code}): invalid gateway credentials or virtual key", status_code=r.status_code, request_id=req_id, model=self.model, error_type="auth")
        if r.status_code == 404:
            raise ModelError(f"Bifrost endpoint not found (HTTP 404) — check BIFROST_GATEWAY_URL={self.gateway_url}", status_code=404, request_id=req_id, model=self.model, error_type="not_found")
        if r.status_code == 429:
            raise ModelError("Bifrost rate limited (HTTP 429)", status_code=429, request_id=req_id, model=self.model, error_type="rate_limit")
        if r.status_code >= 500:
            raise ModelError(f"Bifrost upstream/provider failure (HTTP {r.status_code}): {r.text[:160]}", status_code=r.status_code, request_id=req_id, model=self.model, error_type="upstream")
        if r.status_code != 200:
            raise ModelError(f"Bifrost HTTP {r.status_code}: {r.text[:160]}", status_code=r.status_code, request_id=req_id, model=self.model, error_type="http")

        try:
            d = r.json()
        except Exception as e:
            raise ModelError(f"Bifrost returned non-JSON body: {e}") from e

        # OpenAI-compatible error body
        if "error" in d and not d.get("choices"):
            err = d["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise ModelError(f"Bifrost error: {msg}")

        try:
            choice = d["choices"][0]
            msg = choice.get("message") or {}
            text = msg.get("content") or ""
            if isinstance(text, list):  # rare multi-part
                text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in text)
        except (KeyError, IndexError, TypeError):
            raise ModelError("Bifrost empty completion (no choices)")

        usage = d.get("usage") if isinstance(d.get("usage"), dict) else None
        tin, tout, tcached = parse_openai_usage(usage)

        # Cost if Bifrost/provider reports it. Bifrost v2 returns usage.cost as an
        # object ({input_tokens_cost, output_tokens_cost, request_cost, total_cost});
        # older/other gateways return a plain number.
        cost = parse_gateway_cost(usage)
        if cost is None and isinstance(d.get("bifrost"), dict):
            cost = parse_gateway_cost({"cost": d["bifrost"].get("cost")})

        model_used = d.get("model") or self.model
        # Infer provider from model id prefix
        provider_used = self.agent_provider
        if isinstance(model_used, str) and "/" in model_used:
            provider_used = model_used.split("/", 1)[0]

        if not req_id:
            req_id = d.get("id")  # OpenAI-style completion id

        meta = {
            "request_id": req_id,
            "model": model_used,
            "provider": provider_used,
            "cost": cost,
            "source": "bifrost",
            "status_code": r.status_code,
            "tokens_input": tin,
            "tokens_output": tout,
            "tokens_cached": tcached,
        }
        return text, tin, tout, tcached, meta


# ---------------------------------------------------------------------------
# Legacy direct adapters — retained only for explicit BIFROST_ENABLED=0 escape
# hatch and for unit tests that need to mock them. Normal path never uses them.
# ---------------------------------------------------------------------------

class GeminiAdapter(Adapter):
    provider = "Google AI"

    def _call(self, prompt, *, temperature, max_tokens, timeout, system=None):
        sys_content = system if system is not None else SYSTEM_PROMPT
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": sys_content}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            raise ModelError(f"HTTP {r.status_code}: {r.text[:120]}")
        d = r.json()
        try:
            text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            raise ModelError("empty candidate (blocked or truncated)")
        u = d.get("usageMetadata", {})
        out = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
        meta = {"source": "direct", "model": self.model, "provider": "gemini"}
        return text, u.get("promptTokenCount", 0), out, u.get("cachedContentTokenCount", 0), meta


class OpenRouterAdapter(Adapter):
    provider = "OpenRouter"

    def _call(self, prompt, *, temperature, max_tokens, timeout, system=None):
        model = self.model if "/" in self.model else f"google/{self.model}"
        sys_content = system if system is not None else SYSTEM_PROMPT
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": sys_content},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            raise ModelError(f"HTTP {r.status_code}: {r.text[:120]}")
        d = r.json()
        try:
            text = d["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            raise ModelError("empty completion")
        u = d.get("usage", {})
        cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        meta = {"source": "direct", "model": model, "provider": "openrouter", "request_id": d.get("id")}
        return text, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), cached, meta


def adapter_for(agent: dict, settings) -> Adapter:
    """Build the adapter used for live execution.

    When Bifrost is enabled (default), every request goes through the gateway.
    There is no silent fallback to direct Gemini/OpenRouter calls.
    """
    if getattr(settings, "bifrost_enabled", True):
        model_id = bifrost_model_id(agent)
        return BifrostAdapter(
            gateway_url=settings.bifrost_gateway_url,
            # No placeholder: Bifrost answers 401 "virtual key is required"
            # when x-bf-vk is missing, and 401 "invalid virtual key" when it
            # is wrong. Only a real key is forwarded.
            api_key=settings.bifrost_api_key or "",
            model=model_id,
            agent_provider=agent.get("model_provider", ""),
        )

    # Explicit escape hatch only (BIFROST_ENABLED=0)
    api_key = settings.provider_key(agent["model_provider"])
    p = agent["model_provider"].strip().lower()
    if p in ("google ai", "google", "gemini"):
        return GeminiAdapter(api_key, agent["model"])
    if p == "openrouter":
        return OpenRouterAdapter(api_key, agent["model"])
    raise ModelError(f"unsupported provider '{agent['model_provider']}'")


SUPPORTED_PROVIDERS = {"google ai", "google", "gemini", "openrouter", "bifrost"}


def _env_path_hint() -> str:
    from .config import BACKEND_DIR
    p = BACKEND_DIR / ".env"
    return f"{p} ({'found' if p.exists() else 'NOT FOUND - is it named .env and not .env.txt?'})"


def _auth_error_message(base: str, status_code: int, settings) -> str:
    """Explain an authentication failure in terms the operator can act on."""
    if not (settings.bifrost_api_key or "").strip():
        return (
            f"Gateway reachable at {base} but rejected the request (HTTP {status_code}): "
            "no BIFROST_API_KEY is configured. Bifrost v2 requires a virtual key — "
            "create one in the Bifrost UI (Virtual Keys) and set BIFROST_API_KEY=<key> "
            "in the backend .env (then restart the backend). It is sent as the x-bf-vk header. "
            f"Looked for the file at {_env_path_hint()}."
        )
    return (
        f"Gateway reachable at {base} but rejected our credentials (HTTP {status_code}). "
        "Bifrost v2 expects the virtual key in the x-bf-vk header — check that "
        "BIFROST_API_KEY in the backend .env matches a virtual key created in the "
        "Bifrost UI, and that it has not been revoked."
    )



def probe_chat_completion(
    settings,
    model: str,
    *,
    timeout_sec: float = 8.0,
) -> dict[str, Any]:
    """Actually POST a minimal /v1/chat/completions request.

    A successful /v1/models list does **not** prove completions work (wrong virtual-key
    permissions, model not routed, provider down). This probe exercises the real path.
    Returns a small status dict; never raises.
    """
    base = (settings.bifrost_gateway_url or "").rstrip("/")
    out: dict[str, Any] = {
        "ok": False,
        "model": model,
        "error": None,
        "http_status": None,
        "request_id": None,
        "latency_ms": None,
    }
    if not base:
        out["error"] = "BIFROST_GATEWAY_URL is empty"
        return out
    chat_url = f"{base}/v1/chat/completions" if not base.endswith("/v1/chat/completions") else base
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "bifrost-benchmark-platform/1.0-probe",
    }
    headers.update(bifrost_auth_headers(settings.bifrost_api_key))
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 8,
        "messages": [
            {"role": "system", "content": "Reply with the single word: ok"},
            {"role": "user", "content": "ping"},
        ],
    }
    t0 = time.monotonic()
    try:
        r = httpx.post(chat_url, headers=headers, json=payload, timeout=max(1.0, timeout_sec))
    except httpx.TimeoutException:
        out["error"] = f"chat completion probe timed out after {timeout_sec:.0f}s for model {model}"
        out["latency_ms"] = round((time.monotonic() - t0) * 1000)
        return out
    except httpx.ConnectError as e:
        out["error"] = f"gateway unreachable for chat completion: {e}"
        out["latency_ms"] = round((time.monotonic() - t0) * 1000)
        return out
    except Exception as e:
        out["error"] = f"chat completion probe transport error: {str(e)[:160]}"
        out["latency_ms"] = round((time.monotonic() - t0) * 1000)
        return out

    out["latency_ms"] = round((time.monotonic() - t0) * 1000)
    out["http_status"] = r.status_code
    out["request_id"] = (
        r.headers.get("x-request-id")
        or r.headers.get("x-bifrost-request-id")
        or r.headers.get("cf-ray")
    )
    if r.status_code in (401, 403):
        out["error"] = _auth_error_message(base, r.status_code, settings)
        return out
    if r.status_code == 404:
        out["error"] = f"chat completions endpoint not found (HTTP 404) at {chat_url}"
        return out
    if r.status_code == 429:
        out["error"] = f"rate limited on chat completion probe for model {model}"
        return out
    if r.status_code >= 500:
        out["error"] = f"upstream/provider failure on chat probe (HTTP {r.status_code}): {r.text[:120]}"
        return out
    if r.status_code != 200:
        out["error"] = f"chat completion probe HTTP {r.status_code}: {r.text[:120]}"
        return out
    try:
        d = r.json()
    except Exception as e:
        out["error"] = f"non-JSON chat completion response: {e}"
        return out
    if "error" in d and not d.get("choices"):
        err = d["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        out["error"] = f"Bifrost chat error: {msg}"
        return out
    if not d.get("choices"):
        out["error"] = "chat completion returned no choices"
        return out
    out["ok"] = True
    if not out["request_id"]:
        out["request_id"] = d.get("id")
    return out


def check_gateway_health(settings, *, timeout_sec: float | None = None) -> dict[str, Any]:
    """Probe the Bifrost gateway for reachability, authentication and model availability.

    The probe is bounded by a *total* deadline so it can never hang a health
    check: every HTTP attempt gets whatever is left of the budget, and the
    function returns (never raises) even when the gateway is completely down.

    The returned status distinguishes three different failures that are easy to
    conflate:

    ``unreachable``
        No HTTP response at all — connection refused, DNS failure or timeout.
    ``auth_error``
        The gateway answered, but rejected our credentials (HTTP 401/403).
    ``connected``
        The gateway answered and accepted the request.

    ``authenticated`` says whether our credentials were accepted, and
    ``model_call_path_ok`` says whether the OpenAI-compatible models endpoint
    answered. A successful /v1/models does **not** prove chat completions work;
    use ``probe_chat_completion`` for that before live runs.
    """
    base = (settings.bifrost_gateway_url or "").rstrip("/")
    budget = float(timeout_sec if timeout_sec is not None else getattr(settings, "gateway_probe_timeout_sec", 4.0))
    budget = max(0.5, budget)

    result: dict[str, Any] = {
        "enabled": bool(settings.bifrost_enabled),
        "gateway_url": base,
        "reachable": False,
        "authenticated": False,
        "model_call_path_ok": False,
        "status": "disabled" if not settings.bifrost_enabled else "unknown",
        "error": None,
        "providers": [],
        "models": [],
        "version": None,
        "latency_ms": None,
        "checked_at": time.time(),
    }
    if not settings.bifrost_enabled:
        result["status"] = "disabled"
        result["error"] = "BIFROST_ENABLED=0 — gateway bypassed (direct providers only)"
        return result

    if not base:
        result["status"] = "misconfigured"
        result["error"] = "BIFROST_GATEWAY_URL is empty"
        return result

    t0 = time.monotonic()
    headers = bifrost_auth_headers(settings.bifrost_api_key)

    # The OpenAI-compatible models endpoint is probed first. /health and
    # /metrics are fallbacks for gateways that do not expose a models list.
    # Note: models list success does not prove chat completions work.
    probes = [
        f"{base}/v1/models",
        f"{base}/health",
        f"{base}/metrics",
    ]
    last_err: str | None = None
    for url in probes:
        remaining = budget - (time.monotonic() - t0)
        if remaining <= 0.2:
            last_err = last_err or f"Gateway probe timed out after {budget:.1f}s"
            break
        try:
            r = httpx.get(url, headers=headers, timeout=min(5.0, remaining))
            result["latency_ms"] = round((time.monotonic() - t0) * 1000)
            if r.status_code == 200:
                result["reachable"] = True
                result["authenticated"] = True
                result["status"] = "connected"
                try:
                    body = r.json()
                except Exception:
                    body = {}
                if isinstance(body, dict) and "data" in body and isinstance(body["data"], list):
                    # OpenAI /v1/models shape
                    models = []
                    providers = set()
                    for m in body["data"][:80]:
                        mid = m.get("id") or m.get("name") or ""
                        if mid:
                            models.append(mid)
                            if "/" in mid:
                                providers.add(mid.split("/", 1)[0])
                    result["models"] = models
                    result["providers"] = sorted(providers)
                    result["model_call_path_ok"] = True
                elif isinstance(body, dict) and body.get("status"):
                    result["version"] = body.get("version") or body.get("bifrost_version")
                return result
            if r.status_code in (401, 403):
                # The gateway is up but our credentials are not accepted.
                result["reachable"] = True
                result["authenticated"] = False
                result["status"] = "auth_error"
                result["error"] = _auth_error_message(base, r.status_code, settings)
                return result
            last_err = f"HTTP {r.status_code} from {url}"
        except httpx.TimeoutException:
            last_err = f"Timeout probing {url}"
        except httpx.ConnectError:
            last_err = f"Connection refused — is Bifrost running at {base}?"
        except Exception as e:
            last_err = str(e)[:160]

    result["status"] = "unreachable"
    result["error"] = last_err or "Gateway not reachable"
    result["latency_ms"] = round((time.monotonic() - t0) * 1000)
    return result
