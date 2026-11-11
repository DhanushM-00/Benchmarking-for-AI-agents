"""Stage 1 — Maxim AI Bifrost gateway integration tests.

Uses mocked HTTP responses for automated CI. A real smoke test runs only when
BIFROST_SMOKE=1 and a gateway is reachable.
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.adapters import (
    BifrostAdapter,
    ModelError,
    adapter_for,
    bifrost_model_id,
    check_gateway_health,
    extract_code,
)
from app.config import Settings


# ---------------------------------------------------------------------------
# Unit: model id mapping
# ---------------------------------------------------------------------------

def test_bifrost_model_id_gemini():
    assert bifrost_model_id({"model": "gemini-2.5-pro", "model_provider": "Google AI"}) == "gemini/gemini-2.5-pro"
    assert bifrost_model_id({"model": "gemini-2.5-flash", "model_provider": "gemini"}) == "gemini/gemini-2.5-flash"


def test_bifrost_model_id_openrouter():
    assert bifrost_model_id({"model": "gemini-2.5-pro", "model_provider": "OpenRouter"}) == "openrouter/google/gemini-2.5-pro"
    assert bifrost_model_id({"model": "google/gemini-2.5-pro", "model_provider": "OpenRouter"}) == "openrouter/google/gemini-2.5-pro"


def test_extract_code():
    text = "Here you go:\n```python\nprint(1)\n```\n"
    assert extract_code(text) == "print(1)\n"
    assert extract_code("no code") is None


# ---------------------------------------------------------------------------
# BifrostAdapter — success path (mocked)
# ---------------------------------------------------------------------------

def _ok_response(text: str = "```python\nx = 1\n```", *, prompt_tokens=10, completion_tokens=20, req_id="req-abc"):
    return httpx.Response(
        200,
        json={
            "id": req_id,
            "model": "gemini/gemini-2.5-flash",
            "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "prompt_tokens_details": {"cached_tokens": 3},
            },
        },
        headers={"x-request-id": req_id},
    )


def test_bifrost_success_tokens_and_code():
    adapter = BifrostAdapter("http://localhost:8080", "test-key", "gemini/gemini-2.5-flash")
    with patch("httpx.post", return_value=_ok_response()) as post:
        text, tin, tout, tcached, meta = adapter._call("write a solution", temperature=0.2, max_tokens=1024, timeout=30)
    assert "x = 1" in text
    assert tin == 10 and tout == 20 and tcached == 3
    assert meta["request_id"] == "req-abc"
    assert meta["source"] == "bifrost"
    assert meta["model"] == "gemini/gemini-2.5-flash"
    # Ensure we hit the chat completions path
    assert post.call_args[0][0].endswith("/v1/chat/completions")


def test_bifrost_solve_extracts_code():
    adapter = BifrostAdapter("http://localhost:8080", "test-key", "gemini/gemini-2.5-flash")
    with patch("httpx.post", return_value=_ok_response()):
        gen = adapter.solve("task prompt", temperature=0.1, max_tokens=512, timeout=20)
    assert gen.code is not None
    assert "x = 1" in gen.code
    assert gen.tokens_input == 10
    assert gen.tokens_output == 20
    assert gen.tokens_cached == 3
    assert gen.gateway_request_id == "req-abc"
    assert gen.source == "bifrost"
    assert gen.error is None


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_bifrost_invalid_credentials():
    adapter = BifrostAdapter("http://localhost:8080", "bad-key", "gemini/gemini-2.5-flash")
    with patch("httpx.post", return_value=httpx.Response(401, text="unauthorized")):
        with pytest.raises(ModelError, match="auth failed"):
            adapter._call("p", temperature=0, max_tokens=10, timeout=5)


def test_bifrost_gateway_unavailable():
    adapter = BifrostAdapter("http://localhost:9", "k", "gemini/x")
    with patch("httpx.post", side_effect=httpx.ConnectError("connection refused")):
        with pytest.raises(ModelError, match="unavailable"):
            adapter._call("p", temperature=0, max_tokens=10, timeout=5)


def test_bifrost_provider_failure_5xx():
    adapter = BifrostAdapter("http://localhost:8080", "k", "gemini/x")
    with patch("httpx.post", return_value=httpx.Response(502, text="upstream error")):
        with pytest.raises(ModelError, match="upstream/provider failure"):
            adapter._call("p", temperature=0, max_tokens=10, timeout=5)


def test_bifrost_timeout():
    adapter = BifrostAdapter("http://localhost:8080", "k", "gemini/x")
    with patch("httpx.post", side_effect=httpx.TimeoutException("timed out")):
        with pytest.raises(ModelError, match="timeout"):
            adapter._call("p", temperature=0, max_tokens=10, timeout=1)


def test_bifrost_no_silent_fallback_on_failure():
    """When Bifrost fails, solve() records an error — it does not call Gemini directly."""
    settings = Settings(
        bifrost_enabled=True,
        bifrost_gateway_url="http://localhost:9",
        gemini_api_key="real-gemini-key",
    )
    agent = {"id": "nova-coder", "model": "gemini-2.5-flash", "model_provider": "Google AI"}
    adapter = adapter_for(agent, settings)
    assert isinstance(adapter, BifrostAdapter)
    with patch("httpx.post", side_effect=httpx.ConnectError("down")):
        gen = adapter.solve("prompt", temperature=0.2, max_tokens=256, timeout=5)
    assert gen.error is not None
    assert "unavailable" in gen.error.lower() or "connection" in gen.error.lower()
    assert gen.code is None


# ---------------------------------------------------------------------------
# adapter_for routing
# ---------------------------------------------------------------------------

def test_adapter_for_uses_bifrost_when_enabled():
    settings = Settings(bifrost_enabled=True, bifrost_gateway_url="http://gw:8080")
    agent = {"model": "gemini-2.5-pro", "model_provider": "Google AI"}
    a = adapter_for(agent, settings)
    assert isinstance(a, BifrostAdapter)
    assert a.model == "gemini/gemini-2.5-pro"
    assert a.gateway_url == "http://gw:8080"


def test_adapter_for_escape_hatch_direct():
    settings = Settings(bifrost_enabled=False, gemini_api_key="gk")
    agent = {"model": "gemini-2.5-flash", "model_provider": "Google AI"}
    a = adapter_for(agent, settings)
    from app.adapters import GeminiAdapter
    assert isinstance(a, GeminiAdapter)


# ---------------------------------------------------------------------------
# Gateway health probe
# ---------------------------------------------------------------------------

def test_check_gateway_health_connected():
    settings = Settings(bifrost_enabled=True, bifrost_gateway_url="http://localhost:8080")
    models_body = {
        "data": [
            {"id": "gemini/gemini-2.5-pro"},
            {"id": "openrouter/google/gemini-2.5-flash"},
            {"id": "openai/gpt-4o-mini"},
        ]
    }
    with patch("httpx.get", return_value=httpx.Response(200, json=models_body)):
        st = check_gateway_health(settings)
    assert st["reachable"] is True
    assert st["status"] == "connected"
    assert "gemini" in st["providers"]
    assert len(st["models"]) == 3
    assert st["error"] is None


def test_check_gateway_health_unreachable():
    settings = Settings(bifrost_enabled=True, bifrost_gateway_url="http://localhost:9")
    with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
        st = check_gateway_health(settings)
    assert st["reachable"] is False
    assert st["status"] == "unreachable"
    assert st["error"]


def test_check_gateway_health_disabled():
    settings = Settings(bifrost_enabled=False)
    st = check_gateway_health(settings)
    assert st["status"] == "disabled"
    assert st["reachable"] is False


# ---------------------------------------------------------------------------
# Cost preference in executor (smoke via Generation fields)
# ---------------------------------------------------------------------------

def test_generation_carries_gateway_cost():
    adapter = BifrostAdapter("http://localhost:8080", "k", "gemini/x")
    resp = httpx.Response(
        200,
        json={
            "id": "c1",
            "model": "gemini/x",
            "choices": [{"message": {"content": "```python\npass\n```"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 7, "cost": 0.0012},
        },
    )
    with patch("httpx.post", return_value=resp):
        gen = adapter.solve("p", temperature=0, max_tokens=100, timeout=10)
    assert gen.cost_usd_gateway == pytest.approx(0.0012)
    assert gen.tokens_input == 5


# ---------------------------------------------------------------------------
# Optional real smoke (skipped unless BIFROST_SMOKE=1)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("BIFROST_SMOKE") != "1", reason="set BIFROST_SMOKE=1 for live gateway smoke")
def test_real_gateway_smoke():
    settings = Settings.from_env()
    st = check_gateway_health(settings)
    assert st["reachable"], f"gateway not reachable: {st.get('error')}"
    # Minimal chat call if models are configured
    if not st.get("models"):
        pytest.skip("no models configured in Bifrost UI")
    model = st["models"][0]
    adapter = BifrostAdapter(settings.bifrost_gateway_url, settings.bifrost_api_key or "bifrost", model)
    gen = adapter.solve(
        "Reply with a python code block: def hello(): return 42",
        temperature=0,
        max_tokens=128,
        timeout=45,
    )
    # We only assert the gateway path worked (tokens or request id), not code quality
    assert gen.error is None or gen.gateway_request_id or gen.tokens_input > 0
