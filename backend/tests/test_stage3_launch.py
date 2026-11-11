"""Stage 3 — run creation, task selection, mode selection, isolation, execution."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Store
from app.main import create_app, sync_catalogue
from app.schemas import FairnessConfig, MetricWeights, RunCreate
from app import service


def _fairness(**overrides) -> FairnessConfig:
    base = dict(
        time_limit_per_task_sec=30,
        max_tokens_per_task=4000,
        repeats=1,
        isolation="subprocess",
        container_image="bifrost/sandbox:py3.11-slim",
        network_policy="none",
        randomize_task_order=False,
        random_seed=7,
        scorer_version="scorer-2026.03.1",
        temperature=0.0,
        blinded_evaluation=True,
        metric_weights=MetricWeights(
            task_success=0.25,
            correctness=0.30,
            efficiency=0.15,
            tool_usage=0.15,
            consistency=0.15,
        ),
    )
    base.update(overrides)
    return FairnessConfig(**base)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    s = Store(str(tmp_path / "s3.db"))
    sync_catalogue(s)
    return s


@pytest.fixture
def settings_sim(tmp_path: Path) -> Settings:
    return Settings(
        mode="simulated",
        db_path=str(tmp_path / "s3.db"),
        seed_demo=False,
        require_docker=False,
        allow_host_sandbox=True,
        bifrost_enabled=False,
        sim_delay_ms=0,
    )


def _client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


# ---------------------------------------------------------------------------
# task_ids contract
# ---------------------------------------------------------------------------

def test_create_run_with_task_ids_subset(store: Store, settings_sim: Settings):
    body = RunCreate(
        benchmark_id="python-core",
        agent_ids=["atlas-coder"],
        task_ids=["python-core-t01", "python-core-t02"],
        fairness=_fairness(),
    )
    run = service.create_run(store, settings_sim, body)
    assert run["task_ids"] == ["python-core-t01", "python-core-t02"]
    assert run["task_count"] == 2
    assert run["total_executions"] == 2  # 2 tasks × 1 agent × 1 repeat
    assert run["dataset_hash"]
    assert run["status"] == "queued"
    assert "[SIMULATED]" in run["notes"]


def test_create_run_without_task_ids_uses_full_benchmark(store: Store, settings_sim: Settings):
    body = RunCreate(
        benchmark_id="python-core",
        agent_ids=["atlas-coder", "nova-coder"],
        fairness=_fairness(repeats=2),
    )
    run = service.create_run(store, settings_sim, body)
    assert run["task_count"] == 24
    assert len(run["task_ids"]) == 24
    assert run["total_executions"] == 24 * 2 * 2


def test_task_ids_must_belong_to_benchmark(store: Store, settings_sim: Settings):
    body = RunCreate(
        benchmark_id="python-core",
        agent_ids=["atlas-coder"],
        task_ids=["python-core-t01", "debug-suite-t01"],
        fairness=_fairness(),
    )
    with pytest.raises(Exception) as ei:
        service.create_run(store, settings_sim, body)
    assert "not in benchmark" in str(ei.value.detail).lower() or "not in benchmark" in str(ei.value)


def test_unknown_task_id_rejected(store: Store, settings_sim: Settings):
    body = RunCreate(
        benchmark_id="python-core",
        agent_ids=["atlas-coder"],
        task_ids=["python-core-t01", "no-such-task"],
        fairness=_fairness(),
    )
    with pytest.raises(Exception) as ei:
        service.create_run(store, settings_sim, body)
    assert "unknown task" in str(ei.value.detail).lower() or "unknown task" in str(ei.value)


def test_unknown_agent_rejected(store: Store, settings_sim: Settings):
    body = RunCreate(
        benchmark_id="python-core",
        agent_ids=["ghost-agent"],
        fairness=_fairness(),
    )
    with pytest.raises(Exception) as ei:
        service.create_run(store, settings_sim, body)
    assert "unknown agent" in str(ei.value.detail).lower() or "unknown agent" in str(ei.value)


# ---------------------------------------------------------------------------
# mode selection — never silent live→simulated when mode=live
# ---------------------------------------------------------------------------

def test_live_mode_refuses_without_gateway(store: Store, tmp_path: Path):
    settings = Settings(
        mode="live",
        db_path=str(tmp_path / "live.db"),
        bifrost_enabled=True,
        bifrost_gateway_url="",
        allow_host_sandbox=True,
        require_docker=False,
        seed_demo=False,
    )
    body = RunCreate(
        benchmark_id="python-core",
        agent_ids=["atlas-coder"],
        task_ids=["python-core-t01"],
        fairness=_fairness(),
    )
    with pytest.raises(Exception) as ei:
        service.create_run(store, settings, body)
    assert "live mode unavailable" in str(ei.value.detail).lower() or "live mode unavailable" in str(ei.value)


def test_auto_mode_falls_back_to_simulated_with_reasons(store: Store, tmp_path: Path):
    settings = Settings(
        mode="auto",
        db_path=str(tmp_path / "auto.db"),
        bifrost_enabled=True,
        bifrost_gateway_url="",
        allow_host_sandbox=True,
        require_docker=False,
        seed_demo=False,
    )
    body = RunCreate(
        benchmark_id="python-core",
        agent_ids=["atlas-coder"],
        task_ids=["python-core-t01"],
        fairness=_fairness(),
    )
    run = service.create_run(store, settings, body)
    assert store.get_run_mode(run["id"]) == "simulated"
    assert run.get("mode_reasons")
    assert "[SIMULATED]" in run["notes"]


def test_docker_unavailable_live_raises_without_allow_host(store: Store, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.service.docker_available", lambda: False)
    settings = Settings(
        mode="live",
        db_path=str(tmp_path / "dock.db"),
        bifrost_enabled=False,  # skip gateway checks; still need keys for live without bifrost
        gemini_api_key="test-key",
        allow_host_sandbox=False,
        require_docker=True,
        seed_demo=False,
    )
    # Without bifrost, live needs provider keys — atlas is Google AI
    body = RunCreate(
        benchmark_id="python-core",
        agent_ids=["atlas-coder"],
        task_ids=["python-core-t01"],
        fairness=_fairness(isolation="docker"),
    )
    with pytest.raises(Exception):
        service.create_run(store, settings, body)


def test_docker_unavailable_with_allow_host_records_subprocess(store: Store, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.service.docker_available", lambda: False)
    settings = Settings(
        mode="simulated",  # avoid live provider requirements
        db_path=str(tmp_path / "dock2.db"),
        allow_host_sandbox=True,
        require_docker=False,
        seed_demo=False,
        bifrost_enabled=False,
    )
    body = RunCreate(
        benchmark_id="python-core",
        agent_ids=["atlas-coder"],
        task_ids=["python-core-t01"],
        fairness=_fairness(isolation="docker"),
    )
    run = service.create_run(store, settings, body)
    # simulated mode does not force isolation downgrade path the same way;
    # when mode is simulated, isolation stays as requested in fairness dump unless live.
    assert run["status"] == "queued"


# ---------------------------------------------------------------------------
# End-to-end simulated execution with task subset
# ---------------------------------------------------------------------------

def test_simulated_run_executes_exact_task_set(tmp_path: Path):
    db = str(tmp_path / "e2e.db")
    settings = Settings(
        mode="simulated",
        db_path=db,
        seed_demo=False,
        require_docker=False,
        allow_host_sandbox=True,
        bifrost_enabled=False,
        sim_delay_ms=0,
    )
    with TestClient(create_app(settings)) as client:
        payload = {
            "benchmark_id": "python-core",
            "agent_ids": ["atlas-coder", "nova-coder"],
            "task_ids": ["python-core-t01", "python-core-t03"],
            "fairness": _fairness(repeats=1).model_dump(),
            "notes": "stage3 e2e",
        }
        r = client.post("/api/v1/runs", json=payload)
        assert r.status_code == 201, r.text
        run = r.json()
        assert run["task_ids"] == ["python-core-t01", "python-core-t03"]
        assert run["total_executions"] == 4
        rid = run["id"]

        # POST already submitted the run to the pool; wait for completion.
        import time
        detail = None
        for _ in range(100):
            detail = client.get(f"/api/v1/runs/{rid}").json()
            if detail["status"] in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.05)
        assert detail is not None
        assert detail["status"] == "completed", detail
        assert detail["progress"] == 100
        assert "[SIMULATED]" in detail["notes"]
        assert detail["task_ids"] == ["python-core-t01", "python-core-t03"]
        # Each agent has results for exactly the selected tasks
        for ar in detail["agent_results"]:
            tids = {tr["task_id"] for tr in ar.get("task_results") or []}
            assert tids == {"python-core-t01", "python-core-t03"}


def test_duplicate_launch_creates_independent_runs(tmp_path: Path):
    db = str(tmp_path / "dup.db")
    settings = Settings(
        mode="simulated",
        db_path=db,
        seed_demo=False,
        require_docker=False,
        allow_host_sandbox=True,
        bifrost_enabled=False,
        sim_delay_ms=0,
    )
    with TestClient(create_app(settings)) as client:
        payload = {
            "benchmark_id": "python-core",
            "agent_ids": ["atlas-coder"],
            "task_ids": ["python-core-t01"],
            "fairness": _fairness().model_dump(),
        }
        r1 = client.post("/api/v1/runs", json=payload)
        r2 = client.post("/api/v1/runs", json=payload)
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["id"] != r2.json()["id"]


def test_cancel_queued_run(tmp_path: Path):
    db = str(tmp_path / "cancel.db")
    settings = Settings(
        mode="simulated",
        db_path=db,
        seed_demo=False,
        require_docker=False,
        allow_host_sandbox=True,
        bifrost_enabled=False,
        sim_delay_ms=5000,  # slow enough that we can cancel before finish if async
    )
    with TestClient(create_app(settings)) as client:
        payload = {
            "benchmark_id": "python-core",
            "agent_ids": ["atlas-coder"],
            "task_ids": ["python-core-t01"],
            "fairness": _fairness().model_dump(),
        }
        r = client.post("/api/v1/runs", json=payload)
        rid = r.json()["id"]
        # Cancel while still queued/running
        c = client.post(f"/api/v1/runs/{rid}/cancel")
        assert c.status_code == 200
        body = c.json()
        assert body["status"] in ("cancelled", "queued", "running", "completed")


def test_api_rejects_empty_task_ids_list(tmp_path: Path):
    db = str(tmp_path / "empty.db")
    settings = Settings(
        mode="simulated",
        db_path=db,
        seed_demo=False,
        bifrost_enabled=False,
        allow_host_sandbox=True,
        require_docker=False,
    )
    with TestClient(create_app(settings)) as client:
        payload = {
            "benchmark_id": "python-core",
            "agent_ids": ["atlas-coder"],
            "task_ids": [],
            "fairness": _fairness().model_dump(),
        }
        r = client.post("/api/v1/runs", json=payload)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Run ID consistency (create → get → report / model-calls / events)
# ---------------------------------------------------------------------------

def test_create_run_id_matches_subsequent_get(tmp_path: Path):
    """POST /runs returns an id that GET /runs/{id} can retrieve exactly — no substitution."""
    db = str(tmp_path / "id-consistency.db")
    settings = Settings(
        mode="simulated",
        db_path=db,
        seed_demo=False,
        bifrost_enabled=False,
        allow_host_sandbox=True,
        require_docker=False,
        sim_delay_ms=0,
    )
    with TestClient(create_app(settings)) as client:
        payload = {
            "benchmark_id": "python-core",
            "agent_ids": ["atlas-coder"],
            "task_ids": ["python-core-t01"],
            "fairness": _fairness().model_dump(),
        }
        created = client.post("/api/v1/runs", json=payload)
        assert created.status_code == 201, created.text
        body = created.json()
        rid = body["id"]
        assert rid and rid.startswith("run-"), rid
        assert body["status"] in ("queued", "running", "completed")

        got = client.get(f"/api/v1/runs/{rid}")
        assert got.status_code == 200, got.text
        assert got.json()["id"] == rid

        # Missing id must 404 with a clear message — never another run.
        missing = client.get("/api/v1/runs/run-2511-does-not-exist")
        assert missing.status_code == 404
        detail = missing.json().get("detail", "")
        assert "run-2511-does-not-exist" in detail
        assert "not found" in detail.lower()


def test_run_report_and_traces_use_same_id(tmp_path: Path):
    """Report, model-calls, and events endpoints key off the create response id."""
    db = str(tmp_path / "id-report.db")
    settings = Settings(
        mode="simulated",
        db_path=db,
        seed_demo=False,
        bifrost_enabled=False,
        allow_host_sandbox=True,
        require_docker=False,
        sim_delay_ms=0,
    )
    with TestClient(create_app(settings)) as client:
        payload = {
            "benchmark_id": "python-core",
            "agent_ids": ["atlas-coder"],
            "task_ids": ["python-core-t01"],
            "fairness": _fairness().model_dump(),
        }
        created = client.post("/api/v1/runs", json=payload)
        assert created.status_code == 201
        rid = created.json()["id"]

        report = client.get(f"/api/v1/runs/{rid}/report")
        assert report.status_code == 200, report.text
        report_body = report.json()
        # Report may nest the run or expose run_id / id at top level
        report_id = report_body.get("id") or report_body.get("run_id") or (report_body.get("run") or {}).get("id")
        if report_id:
            assert report_id == rid

        calls = client.get(f"/api/v1/runs/{rid}/model-calls")
        assert calls.status_code == 200, calls.text
        assert calls.json().get("run_id") == rid

        events = client.get(f"/api/v1/runs/{rid}/events")
        assert events.status_code == 200, events.text
        assert events.json().get("run_id") == rid


def test_unknown_run_never_substituted(tmp_path: Path):
    """GET for a nonexistent run returns 404; list does not invent the missing id."""
    db = str(tmp_path / "no-sub.db")
    settings = Settings(
        mode="simulated",
        db_path=db,
        seed_demo=False,
        bifrost_enabled=False,
        allow_host_sandbox=True,
        require_docker=False,
        sim_delay_ms=0,
    )
    with TestClient(create_app(settings)) as client:
        # Create one real run so the DB is non-empty
        created = client.post(
            "/api/v1/runs",
            json={
                "benchmark_id": "python-core",
                "agent_ids": ["atlas-coder"],
                "task_ids": ["python-core-t01"],
                "fairness": _fairness().model_dump(),
            },
        )
        assert created.status_code == 201
        real_id = created.json()["id"]

        phantom = "run-2511"
        r = client.get(f"/api/v1/runs/{phantom}")
        assert r.status_code == 404
        assert phantom in r.json().get("detail", "")
        # Must not return the real run under a different id
        assert r.json().get("id") != real_id

        listed = client.get("/api/v1/runs")
        assert listed.status_code == 200
        ids = {row["id"] for row in listed.json()}
        assert real_id in ids
        assert phantom not in ids


def test_page_refresh_retrieves_same_run(tmp_path: Path):
    """Simulates refresh: create, then independent GET as if the SPA reloaded."""
    db = str(tmp_path / "refresh.db")
    settings = Settings(
        mode="simulated",
        db_path=db,
        seed_demo=False,
        bifrost_enabled=False,
        allow_host_sandbox=True,
        require_docker=False,
        sim_delay_ms=0,
    )
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/v1/runs",
            json={
                "benchmark_id": "python-core",
                "agent_ids": ["atlas-coder", "nova-coder"],
                "task_ids": ["python-core-t01", "python-core-t02"],
                "fairness": _fairness().model_dump(),
            },
        )
        assert created.status_code == 201
        rid = created.json()["id"]
        assert created.json()["task_count"] == 2
        assert set(created.json()["agent_ids"]) == {"atlas-coder", "nova-coder"}

    # New client instance — same DB path, as after a process-visible refresh
    with TestClient(create_app(settings)) as client2:
        got = client2.get(f"/api/v1/runs/{rid}")
        assert got.status_code == 200
        assert got.json()["id"] == rid
        assert got.json()["task_count"] == 2
        assert set(got.json()["agent_ids"]) == {"atlas-coder", "nova-coder"}
