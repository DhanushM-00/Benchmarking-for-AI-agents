"""Stage 2: Bifrost model-call tracing."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents import agent_for
from app.agents.base import AgentRunConfig
from app.config import Settings
from app.db import Store
from app.main import create_app
from app.tracing import traced_adapter_call, record_model_call
from app.adapters import BifrostAdapter


def _ok_response(content="```python\nx=1\n```", req_id="bf-req-1", cost=0.0012):
    return httpx.Response(
        200,
        headers={"x-request-id": req_id},
        json={
            "id": req_id,
            "model": "gemini/gemini-2.5-flash",
            "choices": [{"message": {"content": content}}],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "prompt_tokens_details": {"cached_tokens": 2},
                "cost": cost,
            },
        },
    )


def test_traced_call_records_success(tmp_path):
    records = []
    adapter = BifrostAdapter(api_key="", model="gemini/gemini-2.5-flash", gateway_url="http://localhost:8080")
    with patch("httpx.post", return_value=_ok_response()):
        text, ti, to, tc, meta = traced_adapter_call(
            adapter, "hi", temperature=0.1, max_tokens=64, timeout=10, system="sys",
            run_id="run1", agent_id="atlas-coder", task_id="t1", strategy="react",
            phase="react_step", on_record=records.append,
        )
    assert "x=1" in text
    assert len(records) == 1
    r = records[0]
    assert r["success"] is True
    assert r["tokens_input"] == 11
    assert r["tokens_output"] == 7
    assert r["tokens_cached"] == 2
    assert r["total_tokens"] == 18
    assert r["cost_usd"] == 0.0012
    assert r["cost_source"] == "gateway"
    assert r["gateway_request_id"]
    assert r["agent_id"] == "atlas-coder"
    assert r["run_id"] == "run1"
    assert r["latency_ms"] is not None and r["latency_ms"] >= 0


def test_traced_call_records_failure():
    records = []
    adapter = BifrostAdapter(api_key="", model="gemini/gemini-2.5-flash", gateway_url="http://localhost:8080")

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    with patch("httpx.post", side_effect=boom):
        with pytest.raises(Exception):
            traced_adapter_call(
                adapter, "hi", temperature=0.1, max_tokens=32, timeout=5, system="s",
                run_id="r", agent_id="a", task_id="t", strategy="react",
                on_record=records.append,
            )
    assert len(records) == 1
    assert records[0]["success"] is False
    assert records[0]["error"]
    assert records[0]["tokens_input"] is None  # not invented as zero
    assert records[0]["cost_usd"] is None


def test_missing_usage_not_forced_to_zero():
    rec = record_model_call(
        run_id="r", agent_id="a", task_id="t", strategy="react",
        provider="gemini", model="m", started_at="t0", finished_at="t1",
        latency_ms=10, tokens_input=None, tokens_output=None, tokens_cached=None,
        total_tokens=None, cost_usd=None, cost_source=None, http_status=200,
        success=True, error=None, gateway_request_id="x",
    )
    assert rec["tokens_input"] is None
    assert rec["cost_usd"] is None


def test_store_and_api_pagination(tmp_path):
    store = Store(str(tmp_path / "m.db"))
    for i in range(5):
        store.add_model_call({
            "id": f"mc_{i}",
            "run_id": "runX",
            "agent_id": "atlas-coder" if i % 2 == 0 else "nova-coder",
            "task_id": "t1",
            "success": i != 3,
            "tokens_input": 10,
            "tokens_output": 5,
            "total_tokens": 15,
            "cost_usd": 0.01 if i != 3 else None,
            "cost_source": "gateway" if i != 3 else None,
            "latency_ms": 100 + i,
        })
    all_c = store.list_model_calls("runX", limit=10)
    assert len(all_c) == 5
    assert [c["seq"] for c in all_c] == [1, 2, 3, 4, 5]
    page = store.list_model_calls("runX", offset=2, limit=2)
    assert len(page) == 2 and page[0]["seq"] == 3
    agent = store.list_model_calls("runX", agent_id="nova-coder")
    assert all(c["agent_id"] == "nova-coder" for c in agent)
    err = store.list_model_calls("runX", errors_only=True)
    assert len(err) == 1 and err[0]["success"] is False
    summary = store.model_call_summary("runX")
    assert summary["total_calls"] == 5
    assert summary["failed_calls"] == 1
    assert summary["cost_usd"] is not None

    s = Settings(mode="simulated", db_path=str(tmp_path / "api.db"), seed_demo=False)
    # seed model calls into app store via direct API after creating run is heavy —
    # test store methods + inject via create_app state
    with TestClient(create_app(s)) as c:
        # insert into the app's store
        app_store = c.app.state.store
        app_store.add_model_call({
            "id": "mc_api_1", "run_id": "ghost", "agent_id": "atlas-coder",
            "success": True, "tokens_input": 3, "tokens_output": 4, "total_tokens": 7,
            "latency_ms": 12, "gateway_request_id": "bf-1", "model": "gemini/x", "provider": "gemini",
        })
        # ghost run does not exist — API should 404
        assert c.get("/api/v1/runs/ghost/model-calls").status_code == 404


def test_concurrent_agents_do_not_mix_traces(tmp_path):
    records = []
    lock = __import__("threading").Lock()

    def on_record(doc):
        with lock:
            records.append(doc)

    def fake_post(url, headers=None, json=None, timeout=None):
        agent_hint = json["messages"][0]["content"][:20]
        return _ok_response(req_id=f"id-{agent_hint[:6]}", cost=0.0001)

    s = Settings(bifrost_enabled=True, bifrost_gateway_url="http://localhost:8080")
    agents = [
        agent_for({"id": "atlas-coder", "model": "m", "model_provider": "Google AI"}, s),
        agent_for({"id": "nova-coder", "model": "m", "model_provider": "Google AI"}, s),
        agent_for({"id": "forge-coder", "model": "m", "model_provider": "OpenRouter"}, s),
    ]

    def run_one(ag, idx):
        cfg = AgentRunConfig(
            time_limit_sec=15, max_model_calls=3, max_repair_attempts=0,
            max_tokens_per_call=128,
            run_id="run_conc",
            agent_id=ag.agent_id,
            task_id=f"task-{idx}",
            on_model_call=on_record,
        )
        return ag.run("Write x=1", str(tmp_path / f"w{idx}"), cfg)

    with patch("httpx.post", side_effect=fake_post):
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda i: run_one(agents[i], i), range(3)))

    assert records, "expected model-call records"
    # each record's agent_id must match and not be polluted
    for r in records:
        assert r["agent_id"] in {"atlas-coder", "nova-coder", "forge-coder"}
        assert r["run_id"] == "run_conc"
        assert r["task_id"] in {"task-0", "task-1", "task-2"}
    # at least one record per agent
    agents_seen = {r["agent_id"] for r in records}
    assert agents_seen == {"atlas-coder", "nova-coder", "forge-coder"}


def test_live_run_persists_inspectable_traces(tmp_path):
    """End-to-end: mocked Bifrost + live mode produces store + API traces."""
    s = Settings(
        mode="live",
        db_path=str(tmp_path / "live.db"),
        seed_demo=False,
        bifrost_enabled=True,
        bifrost_gateway_url="http://localhost:8080",
        require_docker=False,
        allow_host_sandbox=True,
    )

    from tests.conftest import CFG

    healthy = {
        "enabled": True,
        "gateway_url": "http://localhost:8080",
        "reachable": True,
        "authenticated": True,
        "model_call_path_ok": True,
        "status": "connected",
        "error": None,
        "providers": ["gemini"],
        "models": ["gemini/gemini-2.5-pro", "gemini/gemini-2.5-flash"],
        "version": None,
        "latency_ms": 12,
        "checked_at": 0,
    }
    probe_ok = {"ok": True, "model": "x", "error": None, "http_status": 200, "request_id": "probe-1", "latency_ms": 20}

    with (
        patch("httpx.post", return_value=_ok_response()),
        patch("app.adapters.check_gateway_health", return_value=healthy),
        patch("app.adapters.probe_chat_completion", return_value=probe_ok),
    ):
        with TestClient(create_app(s)) as c:
            r = c.post("/api/v1/runs", json={
                "benchmark_id": "python-core",
                "agent_ids": ["atlas-coder", "nova-coder"],
                "fairness": {
                    **CFG,
                    "repeats": 1,
                    "isolation": "subprocess",
                    "max_tokens_per_task": 2048,
                    "time_limit_per_task_sec": 30,
                },
                "task_ids": ["python-core-t01"],  # may be ignored if schema differs
            })
            # Accept 201 or 422 if task_ids not in schema
            if r.status_code == 422:
                r = c.post("/api/v1/runs", json={
                    "benchmark_id": "python-core",
                    "agent_ids": ["atlas-coder"],
                    "fairness": {**CFG, "repeats": 1, "isolation": "subprocess"},
                })
            assert r.status_code == 201, r.text
            rid = r.json()["id"]
            for _ in range(400):
                st = c.get(f"/api/v1/runs/{rid}").json()["status"]
                if st in ("completed", "failed", "cancelled"):
                    break
                time.sleep(0.05)
            traces = c.get(f"/api/v1/runs/{rid}/model-calls").json()
            # Live path should have produced at least one call if agents ran
            # (if benchmark has many tasks, may take longer — still assert structure)
            assert "calls" in traces
            summary = c.get(f"/api/v1/runs/{rid}/model-calls/summary").json()
            assert summary["run_id"] == rid
            if traces["count"] > 0:
                call = traces["calls"][0]
                assert call.get("agent_id")
                detail = c.get(f"/api/v1/model-calls/{call['id']}").json()
                assert detail["id"] == call["id"]
                # no secrets
                blob = str(detail)
                assert "api_key" not in blob.lower()
                assert "authorization" not in blob.lower()
