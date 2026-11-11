"""Stage 1 — catalogue sync, task APIs, integrity, and historical preservation."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.catalog import (
    AGENTS,
    BENCHMARKS,
    CATALOGUE_VERSION,
    TASK_TITLES,
    build_catalogue,
    catalogue_integrity,
)
from app.config import Settings
from app.db import Store
from app.main import create_app, seed, sync_catalogue


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture
def store(tmp_db: str) -> Store:
    return Store(tmp_db)


def _client(db_path: str) -> TestClient:
    settings = Settings(
        mode="simulated",
        db_path=db_path,
        seed_demo=False,
        require_docker=False,
        allow_host_sandbox=True,
        bifrost_enabled=False,
    )
    app = create_app(settings)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Static catalogue
# ---------------------------------------------------------------------------

def test_static_catalogue_counts_and_uniqueness():
    benches, tasks = build_catalogue()
    assert len(benches) == 5
    assert len(tasks) == 100
    assert sum(len(v) for v in TASK_TITLES.values()) == 100
    ids = [t["id"] for t, _ in tasks]
    assert len(ids) == len(set(ids)), "task IDs must be unique"
    for b in benches:
        assert b["task_count"] == len(TASK_TITLES[b["id"]])
        assert b["task_count"] == sum(1 for t, _ in tasks if t["benchmark_id"] == b["id"])


def test_every_task_has_hidden_tests():
    _, tasks = build_catalogue()
    missing = [t["id"] for t, h in tasks if not h]
    assert missing == [], f"tasks missing hidden tests: {missing}"


def test_catalogue_integrity_report():
    info = catalogue_integrity()
    assert info["catalogue_version"] == CATALOGUE_VERSION
    assert info["benchmark_count"] == 5
    assert info["task_count"] == 100
    assert info["task_ids_unique"] is True
    assert info["all_live_tasks_have_hidden_tests"] is True
    assert info["tasks_missing_hidden_tests"] == []
    assert set(info["builtin_agent_ids"]) == {a["id"] for a in AGENTS}


# ---------------------------------------------------------------------------
# Fresh database
# ---------------------------------------------------------------------------

def test_fresh_db_sync_exposes_full_catalogue(store: Store):
    assert store.count_benchmarks() == 0
    result = sync_catalogue(store)
    assert result["benchmarks_synced"] == 5
    assert result["tasks_synced"] == 100
    assert result["db_task_count"] == 100
    assert store.count_benchmarks() == 5
    assert store.count_tasks() == 100
    agents = store.list_agents()
    assert {a["id"] for a in agents} >= {a["id"] for a in AGENTS}
    for bid in [b["id"] for b in BENCHMARKS]:
        assert store.get_benchmark(bid) is not None
        assert store.count_tasks(bid) == len(TASK_TITLES[bid])
    # sample task detail
    t = store.get_task("python-core-t01")
    assert t is not None
    assert t["benchmark_id"] == "python-core"
    assert store.has_hidden_tests("python-core-t01")


# ---------------------------------------------------------------------------
# Partially populated / older database
# ---------------------------------------------------------------------------

def test_partial_db_receives_missing_catalogue_rows(store: Store):
    """Simulate an old DB that only had the first benchmark."""
    benches, tasks = build_catalogue()
    # Seed only python-core (first 24 tasks) and one agent
    store.put_benchmark(benches[0], 0)
    for i, (t, h) in enumerate(tasks):
        if t["benchmark_id"] != "python-core":
            continue
        store.put_task(t, i, h)
    store.put_agent(AGENTS[0])
    assert store.count_benchmarks() == 1
    assert store.count_tasks() == 24

    # User-created agent must survive
    store.put_agent({
        "id": "custom-user-agent",
        "name": "Custom",
        "model": "x",
        "model_provider": "Custom",
        "description": "user",
        "system_prompt_version": "sys-1",
        "tools": [],
        "orchestration": "none",
        "memory": "None",
        "color_index": 3,
        "enabled": True,
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
        "registered_at": "2026-01-01T00:00:00Z",
    })

    sync_catalogue(store)

    assert store.count_benchmarks() == 5
    assert store.count_tasks() == 100
    assert store.get_agent("custom-user-agent") is not None
    assert store.get_agent("nova-coder") is not None
    assert store.get_agent("forge-coder") is not None
    # All benchmarks present
    for b in BENCHMARKS:
        assert store.get_benchmark(b["id"]) is not None


def test_repeated_startup_does_not_duplicate(store: Store):
    sync_catalogue(store)
    sync_catalogue(store)
    sync_catalogue(store)
    assert store.count_benchmarks() == 5
    assert store.count_tasks() == 100
    # agents: built-ins only once each
    agents = store.list_agents()
    ids = [a["id"] for a in agents]
    for aid in [a["id"] for a in AGENTS]:
        assert ids.count(aid) == 1


def test_historical_runs_preserved(store: Store):
    sync_catalogue(store)
    run_doc = {
        "id": "",
        "name": "historical",
        "benchmark_id": "python-core",
        "benchmark_name": "Python Fundamentals",
        "agent_ids": ["atlas-coder"],
        "agent_results": [],
        "status": "completed",
        "fairness": {},
        "fairness_report": {},
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:01:00Z",
        "duration_sec": 60,
        "progress": 100,
        "notes": "keep me",
        "created_by": "test",
    }
    inserted = store.insert_run(run_doc, "simulated")
    rid = inserted["id"]
    assert store.get_run(rid) is not None

    # Simulate missing catalogue rows then resync
    sync_catalogue(store)
    assert store.get_run(rid) is not None
    assert store.get_run(rid)["notes"] == "keep me"
    assert store.count_tasks() == 100


# ---------------------------------------------------------------------------
# API: tasks by id, filters, agents, integrity
# ---------------------------------------------------------------------------

def test_api_full_catalogue_and_task_detail(tmp_db: str):
    with _client(tmp_db) as client:
        r = client.get("/api/v1/benchmarks")
        assert r.status_code == 200
        benches = r.json()
        assert len(benches) == 5
        assert sum(b["task_count"] for b in benches) == 100
        for b in benches:
            assert b["task_count"] == client.get(f"/api/v1/benchmarks/{b['id']}/tasks").json().__len__()

        r = client.get("/api/v1/tasks")
        assert r.status_code == 200
        all_tasks = r.json()
        assert isinstance(all_tasks, list)
        assert len(all_tasks) == 100

        r = client.get("/api/v1/tasks/python-core-t01")
        assert r.status_code == 200
        task = r.json()
        assert task["id"] == "python-core-t01"
        assert "prompt" in task
        assert "hidden_tests" not in task  # never exposed

        r = client.get("/api/v1/tasks/does-not-exist")
        assert r.status_code == 404

        r = client.get("/api/v1/benchmarks/python-core/tasks", params={"difficulty": "easy"})
        assert r.status_code == 200
        easy = r.json()
        assert all(t["difficulty"] == "easy" for t in easy)
        assert len(easy) < 24

        r = client.get("/api/v1/tasks", params={"search": "palindrome", "limit": 5})
        assert r.status_code == 200
        found = r.json()
        assert len(found) >= 1
        assert any("palindrome" in t["title"].lower() for t in found)

        r = client.get("/api/v1/benchmarks/python-core/tasks", params={"difficulty": "invalid"})
        assert r.status_code == 422


def test_api_agents_no_silent_substitution(tmp_db: str):
    with _client(tmp_db) as client:
        r = client.get("/api/v1/agents")
        assert r.status_code == 200
        agents = r.json()
        assert {a["id"] for a in agents} >= {"atlas-coder", "nova-coder", "forge-coder"}

        r = client.get("/api/v1/agents/atlas-coder")
        assert r.status_code == 200
        assert r.json()["id"] == "atlas-coder"

        r = client.get("/api/v1/agents/totally-unknown-agent")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()


def test_api_catalogue_integrity(tmp_db: str):
    with _client(tmp_db) as client:
        r = client.get("/api/v1/catalogue/integrity")
        assert r.status_code == 200
        body = r.json()
        assert body["catalogue_version"] == CATALOGUE_VERSION
        assert body["task_count"] == 100
        assert body["db_task_count"] == 100
        assert body["db_matches_catalogue"] is True
        assert body["all_live_tasks_have_hidden_tests"] is True
        assert body["missing_tasks_in_db"] == []


def test_api_health_has_catalogue_info(tmp_db: str):
    with _client(tmp_db) as client:
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["catalogue_version"] == CATALOGUE_VERSION
        assert body["task_count"] == 100
        assert body["benchmark_count"] == 5
        # Never expose keys
        blob = json.dumps(body)
        assert "sk-" not in blob
        assert "api_key" not in blob.lower() or body.get("providers") is not None


def test_create_run_rejects_unknown_agent(tmp_db: str):
    with _client(tmp_db) as client:
        payload = {
            "benchmark_id": "python-core",
            "agent_ids": ["does-not-exist-agent"],
            "fairness": {
                "time_limit_per_task_sec": 120,
                "max_tokens_per_task": 32000,
                "repeats": 1,
                "isolation": "subprocess",
                "container_image": "bifrost/sandbox:py3.11-slim",
                "network_policy": "none",
                "randomize_task_order": False,
                "random_seed": 1,
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
            },
        }
        r = client.post("/api/v1/runs", json=payload)
        assert r.status_code == 422
        assert "unknown agent" in r.json()["detail"].lower()


def test_seed_alias_calls_sync(store: Store):
    seed(store)
    assert store.count_tasks() == 100
    seed(store)  # second call still safe
    assert store.count_tasks() == 100
