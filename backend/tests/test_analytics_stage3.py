"""Stage 3: failure analytics and comparison from stored data."""
from __future__ import annotations

from app.analytics import (
    classify_failure,
    extract_failures,
    recovery_analytics,
    agent_comparison,
    build_analytics,
    build_benchmark_report,
)


def test_classify_not_everything_is_agent():
    assert classify_failure(error="Bifrost gateway unavailable", error_category="model_api") == "bifrost_gateway"
    assert classify_failure(error="HTTP 500 from provider", error_category="model_api") == "provider_model"
    assert classify_failure(error="Sandbox timeout", error_category="timeout", timed_out=True) == "timeout"
    assert classify_failure(error="Tests failed: test_x", error_category="incorrect") == "hidden_test"
    assert classify_failure(error="unknown tool foo", error_category="tool") == "invalid_tool_args"
    assert classify_failure(error="Token budget exceeded", error_category="budget") == "budget"


def _run(agent_results, status="completed", mode="live", rid="r1", bench="python-core"):
    return {
        "id": rid,
        "status": status,
        "mode": mode,
        "benchmark_id": bench,
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:10:00Z",
        "fairness_report": {"score": 90, "violations": [], "checks": []},
        "agent_results": agent_results,
    }


def _agent(aid, tasks):
    return {
        "agent_id": aid,
        "id": aid,
        "agent_name": aid,
        "name": aid,
        "model": "m",
        "model_provider": "Google AI",
        "metrics": {"task_success": 50},
        "overall_score": 50,
        "total_tokens": sum((t.get("tokens_input") or 0) + (t.get("tokens_output") or 0) for t in tasks),
        "total_cost_usd": sum(t.get("cost_usd") or 0 for t in tasks),
        "avg_execution_time_sec": 1.0,
        "task_results": tasks,
    }


def test_extract_failures_and_recovery():
    tasks_atlas = [
        {
            "task_id": "python-core-t01",
            "completed": False,
            "error": "Tests failed",
            "error_category": "incorrect",
            "repair_attempts": 2,
            "recovered": False,
            "tokens_input": 10,
            "tokens_output": 5,
            "cost_usd": 0.01,
            "unit_tests_passed": 1,
            "unit_tests_total": 3,
            "execution_time_sec": 2,
            "tool_calls": [{"tool": "fs_write", "outcome": "success"}],
        },
        {
            "task_id": "python-core-t02",
            "completed": True,
            "error": None,
            "repair_attempts": 1,
            "recovered": True,
            "tokens_input": 8,
            "tokens_output": 4,
            "cost_usd": 0.02,
            "unit_tests_passed": 2,
            "unit_tests_total": 2,
            "execution_time_sec": 1.5,
            "tool_calls": [],
        },
    ]
    tasks_nova = [
        {
            "task_id": "python-core-t01",
            "completed": True,
            "error": None,
            "repair_attempts": 0,
            "recovered": False,
            "tokens_input": 12,
            "tokens_output": 6,
            "cost_usd": 0.015,
            "unit_tests_passed": 3,
            "unit_tests_total": 3,
            "execution_time_sec": 1.2,
            "tool_calls": [{"tool": "shell", "outcome": "error"}],
        },
    ]
    runs = [
        _run([_agent("atlas-coder", tasks_atlas), _agent("nova-coder", tasks_nova)]),
    ]
    failures = extract_failures(runs)
    assert any(f["category"] == "hidden_test" for f in failures)
    rec = recovery_analytics(runs, failures)
    assert rec["successful_recoveries"] >= 1
    assert rec["total_retries"] >= 3
    assert rec["recovery_rate"] is not None

    comp = agent_comparison(runs)
    assert len(comp["agents"]) == 2
    by_id = {a["agent_id"]: a for a in comp["agents"]}
    assert by_id["nova-coder"]["task_success_rate"] == 100.0
    assert by_id["atlas-coder"]["task_success_rate"] == 50.0
    assert by_id["atlas-coder"]["recovery_rate"] is not None

    analytics = build_analytics(runs)
    assert analytics["source"] == "stored_runs"
    assert analytics["demo_data"] is False if "demo_data" in analytics else analytics["data_quality"]["demo_data"] is False
    assert analytics["comparison"]["runs_used"] == 1


def test_incomplete_run_not_counted_as_success():
    runs = [
        _run([_agent("atlas-coder", [{
            "task_id": "t1", "completed": True, "unit_tests_passed": 1, "unit_tests_total": 1,
            "tokens_input": 1, "tokens_output": 1, "execution_time_sec": 1, "tool_calls": [],
        }])], status="running"),
    ]
    comp = agent_comparison(runs)
    assert comp["runs_used"] == 0
    assert comp["agents"] == []
    assert any("No completed" in w for w in comp["fairness_warnings"])


def test_benchmark_report():
    run = _run([_agent("forge-coder", [{
        "task_id": "python-core-t01",
        "completed": False,
        "error": "Bifrost gateway unavailable at localhost",
        "error_category": "model_api",
        "repair_attempts": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        "execution_time_sec": 0.5,
        "unit_tests_passed": 0,
        "unit_tests_total": 2,
        "tool_calls": [],
    }])])
    report = build_benchmark_report(run)
    assert report["data_source"] == "stored_run"
    assert report["run_id"] == "r1"
    assert report["agents_tested"]
    assert report["failure_analysis"]["failures"]
    assert report["failure_analysis"]["failures"][0]["category"] == "bifrost_gateway"


def test_analytics_api(tmp_path):
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    from tests.conftest import CFG
    import time

    s = Settings(mode="simulated", db_path=str(tmp_path / "a.db"), seed_demo=False)
    with TestClient(create_app(s)) as c:
        r = c.post("/api/v1/runs", json={
            "benchmark_id": "python-core",
            "agent_ids": ["atlas-coder", "nova-coder", "forge-coder"],
            "fairness": {**CFG, "repeats": 1, "isolation": "subprocess"},
        })
        assert r.status_code == 201
        rid = r.json()["id"]
        for _ in range(200):
            if c.get(f"/api/v1/runs/{rid}").json()["status"] in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.05)
        an = c.get("/api/v1/analytics").json()
        assert an["source"] == "stored_runs"
        assert "comparison" in an and "recovery" in an
        report = c.get(f"/api/v1/runs/{rid}/report").json()
        assert report["run_id"] == rid
        assert "conclusions" in report
        dash = c.get("/api/v1/dashboard").json()
        assert dash.get("data_source") == "stored_runs"
        assert "analytics" in dash
