"""Phase 5 — backend connection detection.

The bugs these tests pin down:

* ``/api/v1/health`` used to probe the Bifrost gateway inline, so a *dead
  gateway* made the *backend* look unreachable to the frontend (which timed out
  at 8s while the probe could take 15s). Health must answer fast and must
  always report ``status == "ok"`` — the gateway's state is reported separately.
* Gateway status must distinguish "cannot reach it" from "reached it but the
  credentials were rejected", and must never be hardcoded.
* The gateway probe must respect a total deadline instead of hanging.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import api as api_module
from app.adapters import check_gateway_health
from app.config import Settings
from app.main import create_app
from app.adapters import BifrostAdapter, ModelError
from tests.fake_gateway import MODE_VK, FakeGateway, free_port


@pytest.fixture()
def gateway():
    gw = FakeGateway()
    yield gw
    gw.stop()


@pytest.fixture()
def dead_port() -> int:
    """A port with nothing listening on it."""
    return free_port()


@pytest.fixture(autouse=True)
def _reset_gateway_cache():
    """The gateway cache is module-level state — keep tests independent."""
    api_module._gateway_cache = {}
    api_module._gateway_cache_at = 0.0
    yield
    api_module._gateway_cache = {}
    api_module._gateway_cache_at = 0.0


def _client(tmp_path, **overrides) -> TestClient:
    params = dict(
        mode="simulated",
        db_path=str(tmp_path / "t.db"),
        sim_delay_ms=0,
        seed_demo=False,
        bifrost_enabled=True,
        bifrost_gateway_url="http://127.0.0.1:9",
    )
    params.update(overrides)
    return TestClient(create_app(Settings(**params)))


# --------------------------------------------------------------------------- #
# check_gateway_health
# --------------------------------------------------------------------------- #


def test_probe_reports_connected_against_a_live_gateway(gateway):
    st = check_gateway_health(
        Settings(bifrost_enabled=True, bifrost_gateway_url=gateway.url), timeout_sec=4
    )
    assert st["reachable"] is True
    assert st["authenticated"] is True
    assert st["model_call_path_ok"] is True
    assert st["status"] == "connected"
    assert st["error"] is None
    assert "gemini" in st["providers"]
    assert len(st["models"]) == 2


def test_probe_distinguishes_authentication_failure_from_unreachable(gateway):
    gateway.set_mode("unauthorized")
    st = check_gateway_health(
        Settings(bifrost_enabled=True, bifrost_gateway_url=gateway.url), timeout_sec=4
    )
    # The gateway answered — that is not the same as being unreachable.
    assert st["reachable"] is True
    assert st["authenticated"] is False
    assert st["model_call_path_ok"] is False
    assert st["status"] == "auth_error"
    assert "401" in st["error"]
    assert st["providers"] == [] and st["models"] == []


def test_probe_treats_403_as_an_authentication_failure(gateway):
    gateway.set_mode("forbidden")
    st = check_gateway_health(
        Settings(bifrost_enabled=True, bifrost_gateway_url=gateway.url), timeout_sec=4
    )
    assert st["reachable"] is True
    assert st["authenticated"] is False
    assert st["status"] == "auth_error"


def test_probe_reports_unreachable_when_nothing_is_listening(dead_port):
    st = check_gateway_health(
        Settings(bifrost_enabled=True, bifrost_gateway_url=f"http://127.0.0.1:{dead_port}"),
        timeout_sec=2,
    )
    assert st["reachable"] is False
    assert st["authenticated"] is False
    assert st["model_call_path_ok"] is False
    assert st["status"] == "unreachable"
    assert st["error"]


def test_probe_reports_disabled_when_the_gateway_is_bypassed():
    st = check_gateway_health(Settings(bifrost_enabled=False))
    assert st["status"] == "disabled"
    assert st["reachable"] is False
    assert st["error"]


def test_probe_reports_misconfigured_when_the_url_is_empty():
    st = check_gateway_health(Settings(bifrost_enabled=True, bifrost_gateway_url=""))
    assert st["status"] == "misconfigured"
    assert st["reachable"] is False


def test_probe_never_raises_when_the_gateway_is_down(dead_port):
    st = check_gateway_health(
        Settings(bifrost_enabled=True, bifrost_gateway_url=f"http://127.0.0.1:{dead_port}"),
        timeout_sec=2,
    )
    assert st["status"] == "unreachable"


def test_probe_respects_its_total_deadline(gateway):
    """A hanging gateway must not hang the probe."""
    gateway.set_mode("slow")
    t0 = time.monotonic()
    st = check_gateway_health(
        Settings(bifrost_enabled=True, bifrost_gateway_url=gateway.url), timeout_sec=1.5
    )
    elapsed = time.monotonic() - t0
    assert elapsed < 6.0, f"probe took {elapsed:.2f}s — the deadline was not honoured"
    assert st["status"] == "unreachable"
    assert st["reachable"] is False


def test_probe_does_not_exceed_the_budget_across_several_attempts(dead_port):
    """The budget is total, not per-probe."""
    t0 = time.monotonic()
    check_gateway_health(
        Settings(bifrost_enabled=True, bifrost_gateway_url=f"http://127.0.0.1:{dead_port}"),
        timeout_sec=1.0,
    )
    assert time.monotonic() - t0 < 3.0


# --------------------------------------------------------------------------- #
# /api/v1/health
# --------------------------------------------------------------------------- #


def test_health_is_ok_even_when_the_gateway_is_down(tmp_path, dead_port):
    """A dead Bifrost gateway must never make Bifrost itself look offline."""
    with _client(tmp_path, bifrost_gateway_url=f"http://127.0.0.1:{dead_port}") as c:
        r = c.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["bifrost"]["reachable"] is False
    assert body["bifrost"]["status"] in ("unreachable", "unknown", "misconfigured")


def test_health_answers_promptly_while_the_gateway_is_hanging(tmp_path, gateway):
    """The frontend health timeout is ~6s — /health must not block on the gateway."""
    gateway.set_mode("slow")
    with _client(tmp_path, bifrost_gateway_url=gateway.url) as c:
        t0 = time.monotonic()
        r = c.get("/api/v1/health")
        elapsed = time.monotonic() - t0
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert elapsed < 3.0, f"/health took {elapsed:.2f}s"


def test_health_reports_the_live_gateway_state(tmp_path, gateway):
    with _client(tmp_path, bifrost_gateway_url=gateway.url) as c:
        body = c.get("/api/v1/health").json()
    assert body["bifrost"]["enabled"] is True
    assert body["bifrost"]["gateway_url"] == gateway.url
    assert body["bifrost"]["status"] in ("connected", "unreachable", "auth_error")


def test_health_never_leaks_the_api_key(tmp_path, gateway):
    with _client(tmp_path, bifrost_gateway_url=gateway.url, bifrost_api_key="sk-secret-value") as c:
        raw = c.get("/api/v1/health").text
    assert "sk-secret-value" not in raw


# --------------------------------------------------------------------------- #
# /api/v1/gateway/status
# --------------------------------------------------------------------------- #


def test_gateway_status_is_fresh_and_never_hardcoded(tmp_path, gateway):
    with _client(tmp_path, bifrost_gateway_url=gateway.url) as c:
        first = c.get("/api/v1/gateway/status").json()
        assert first["status"] == "connected"
        assert first["reachable"] is True
        assert first["models"]

        # The gateway changes behaviour — the next call must notice.
        gateway.set_mode("unauthorized")
        second = c.get("/api/v1/gateway/status").json()

    assert second["status"] == "auth_error"
    assert second["reachable"] is True
    assert second["authenticated"] is False
    assert second["error"]


def test_gateway_status_reports_unreachable_when_the_gateway_is_down(tmp_path, dead_port):
    with _client(tmp_path, bifrost_gateway_url=f"http://127.0.0.1:{dead_port}") as c:
        body = c.get("/api/v1/gateway/status").json()
    assert body["status"] == "unreachable"
    assert body["reachable"] is False
    assert body["error"]


def test_gateway_status_is_bounded_when_the_gateway_hangs(tmp_path, gateway):
    gateway.set_mode("slow")
    with _client(tmp_path, bifrost_gateway_url=gateway.url) as c:
        t0 = time.monotonic()
        r = c.get("/api/v1/gateway/status")
        elapsed = time.monotonic() - t0
    assert r.status_code == 200
    assert r.json()["status"] == "unreachable"
    assert elapsed < 8.0, f"/gateway/status took {elapsed:.2f}s"


def test_gateway_status_never_leaks_the_api_key(tmp_path, gateway):
    with _client(tmp_path, bifrost_gateway_url=gateway.url, bifrost_api_key="sk-secret-value") as c:
        raw = c.get("/api/v1/gateway/status").text
    assert "sk-secret-value" not in raw


def test_health_stays_ok_after_the_gateway_dies(tmp_path, gateway):
    """Scenario C: the gateway disappears — the backend must stay connected."""
    with _client(tmp_path, bifrost_gateway_url=gateway.url) as c:
        assert c.get("/api/v1/health").json()["bifrost"]["status"] == "connected"
        gateway.stop()
        r = c.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# --------------------------------------------------------------------------- #
# Bifrost v2 virtual key (x-bf-vk)
#
# Bifrost v2.5 answers `401 virtual key is required. Provide a virtual key via
# the x-bf-vk header.` when the key is missing or sent only as an
# `Authorization` header — so both the probe and the live adapter have to
# forward the key the way Bifrost expects it.
# --------------------------------------------------------------------------- #


def test_probe_sends_the_virtual_key_in_the_x_bf_vk_header():
    gw = FakeGateway(MODE_VK, virtual_key="sk-bf-real")
    try:
        st = check_gateway_health(
            Settings(
                bifrost_enabled=True,
                bifrost_gateway_url=gw.url,
                bifrost_api_key="sk-bf-real",
            ),
            timeout_sec=4,
        )
        assert st["status"] == "connected", st
        assert st["authenticated"] is True
        assert st["model_call_path_ok"] is True
        assert st["models"] == ["gemini/gemini-2.5-pro"]
        # The key really travelled in x-bf-vk.
        assert gw.requests[-1]["headers"].get("x-bf-vk") == "sk-bf-real"
    finally:
        gw.stop()


def test_probe_reports_auth_error_when_the_virtual_key_is_missing():
    gw = FakeGateway(MODE_VK, virtual_key="sk-bf-real")
    try:
        st = check_gateway_health(
            Settings(bifrost_enabled=True, bifrost_gateway_url=gw.url, bifrost_api_key=""),
            timeout_sec=4,
        )
        assert st["status"] == "auth_error", st
        assert st["reachable"] is True
        assert st["authenticated"] is False
        # The message has to tell the operator exactly what to do.
        assert "BIFROST_API_KEY" in st["error"]
        assert "x-bf-vk" in st["error"]
        # No placeholder credentials are sent when no key is configured.
        sent = gw.requests[-1]["headers"]
        assert "x-bf-vk" not in sent
        assert "authorization" not in sent
    finally:
        gw.stop()


def test_probe_reports_auth_error_when_the_virtual_key_is_wrong():
    gw = FakeGateway(MODE_VK, virtual_key="sk-bf-real")
    try:
        st = check_gateway_health(
            Settings(
                bifrost_enabled=True,
                bifrost_gateway_url=gw.url,
                bifrost_api_key="sk-bf-wrong",
            ),
            timeout_sec=4,
        )
        assert st["status"] == "auth_error", st
        assert st["reachable"] is True
        assert st["authenticated"] is False
        assert "x-bf-vk" in st["error"]
    finally:
        gw.stop()


def test_live_adapter_sends_the_virtual_key_header():
    gw = FakeGateway(MODE_VK, virtual_key="sk-bf-real")
    try:
        adapter = BifrostAdapter(gw.url, "sk-bf-real", "gemini/gemini-2.5-pro")
        gen = adapter.solve("hello", temperature=0, max_tokens=100, timeout=10)
        assert "pass" in (gen.code or "")
        post = [r for r in gw.requests if r["method"] == "POST"][-1]
        assert post["path"].endswith("/v1/chat/completions")
        assert post["headers"].get("x-bf-vk") == "sk-bf-real"
    finally:
        gw.stop()


def test_live_adapter_reports_an_auth_failure_clearly():
    gw = FakeGateway(MODE_VK, virtual_key="sk-bf-real")
    try:
        adapter = BifrostAdapter(gw.url, "sk-bf-wrong", "gemini/gemini-2.5-pro")
        gen = adapter.solve("hello", temperature=0, max_tokens=100, timeout=10)
        # The adapter surfaces the auth failure instead of silently returning
        # an empty answer.
        assert gen.error, "the auth failure must not be swallowed"
        assert "auth" in gen.error.lower()
    finally:
        gw.stop()
