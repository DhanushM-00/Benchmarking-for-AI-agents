"""Stage 2 — tools, agent strategies, hidden-test expansion, fairness of interface."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.agents import agent_for
from app.agents.base import AgentRunConfig
from app.agents.tools import ToolContext, dispatch_tool, tool_fs_read, tool_fs_write, tool_lint
from app.config import Settings
from app.hidden_tests import SPECS


@pytest.fixture()
def workspace(tmp_path):
    return tmp_path


def test_tools_fs_roundtrip(workspace):
    ctx = ToolContext(workspace=workspace)
    out = tool_fs_write(ctx, "solution.py", "x = 1\n")
    assert out.startswith("OK")
    assert tool_fs_read(ctx, "solution.py") == "x = 1\n"
    assert ctx.history[0]["tool"] == "fs_write" and ctx.history[0]["seq"] == 1
    assert ctx.history[1]["tool"] == "fs_read" and ctx.history[1]["outcome"] == "success"


def test_tools_reject_path_escape(workspace):
    ctx = ToolContext(workspace=workspace)
    out = dispatch_tool(ctx, "fs_read", {"path": "../../etc/passwd"})
    assert "ERROR" in out
    assert ctx.history[-1]["outcome"] in ("error", "rejected")


def test_lint_syntax_error(workspace):
    ctx = ToolContext(workspace=workspace)
    tool_fs_write(ctx, "solution.py", "def oops(:\n  pass\n")
    out = tool_lint(ctx, "solution.py")
    assert "SyntaxError" in out


def test_hidden_tests_expanded():
    assert len(SPECS) == 100
    # coverage across catalogues
    assert any(k.startswith("python-core-") for k in SPECS)
    assert any(k.startswith("debug-suite-") for k in SPECS)
    assert any(k.startswith("api-dev-") for k in SPECS)
    assert any(k.startswith("file-io-stats-") for k in SPECS)
    assert any(k.startswith("swe-lite-") for k in SPECS)
    for tid, spec in SPECS.items():
        assert "prompt" in spec and "tests" in spec
        assert "def test_" in spec["tests"]


def _fake_completion(code: str = "def hello():\n    return 42\n"):
    body = {
        "id": "cmpl-1",
        "model": "gemini/gemini-2.5-flash",
        "choices": [{"message": {"content": f"```python\n{code}\n```"}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 30, "prompt_tokens_details": {"cached_tokens": 2}},
    }
    return httpx.Response(200, json=body, headers={"x-request-id": "r1"})


def test_agent_factory_routes_strategies():
    s = Settings(bifrost_enabled=True, bifrost_gateway_url="http://localhost:8080")
    assert agent_for({"id": "atlas-coder", "model": "m", "model_provider": "Google AI"}, s).strategy_name == "react"
    assert agent_for({"id": "nova-coder", "model": "m", "model_provider": "Google AI"}, s).strategy_name == "plan_act_verify"
    assert agent_for({"id": "forge-coder", "model": "m", "model_provider": "OpenRouter"}, s).strategy_name == "state_machine"


def test_nova_plan_act_verify_writes_solution(workspace):
    s = Settings(bifrost_enabled=True, bifrost_gateway_url="http://localhost:8080")
    agent = agent_for({"id": "nova-coder", "model": "gemini-2.5-flash", "model_provider": "Google AI"}, s)
    cfg = AgentRunConfig(time_limit_sec=30, max_model_calls=6, max_repair_attempts=1, max_tokens_per_call=512)

    plan = httpx.Response(200, json={
        "id": "1", "model": "m",
        "choices": [{"message": {"content": "1. write function\n2. return value"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5},
    })
    code_resp = _fake_completion("def hello():\n    return 42\n")

    with patch("httpx.post", side_effect=[plan, code_resp, code_resp]):
        result = agent.run("Write hello() that returns 42.", str(workspace), cfg)

    assert result.strategy == "plan_act_verify"
    assert result.model_calls >= 2
    assert result.code is not None
    assert "42" in result.code
    assert any(s["phase"] == "plan" for s in result.steps)
    assert (workspace / "solution.py").exists()


def test_forge_state_machine_transitions(workspace):
    s = Settings(bifrost_enabled=True, bifrost_gateway_url="http://localhost:8080")
    agent = agent_for({"id": "forge-coder", "model": "gemini-2.5-pro", "model_provider": "OpenRouter"}, s)
    cfg = AgentRunConfig(time_limit_sec=30, max_model_calls=6, max_repair_attempts=1)

    plan = httpx.Response(200, json={
        "id": "1", "model": "m",
        "choices": [{"message": {"content": "1. implement"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 3},
    })
    code_resp = _fake_completion("x = 1\n")
    with patch("httpx.post", side_effect=[plan, code_resp]):
        result = agent.run("Set x = 1 in solution.py", str(workspace), cfg)

    assert result.strategy == "state_machine"
    assert result.code is not None
    phases = [s["phase"] for s in result.steps]
    assert "plan" in phases and "code" in phases
    assert any(s["phase"] == "graph" for s in result.steps)


def test_react_implicit_code_block(workspace):
    s = Settings(bifrost_enabled=True, bifrost_gateway_url="http://localhost:8080")
    agent = agent_for({"id": "atlas-coder", "model": "gemini-2.5-pro", "model_provider": "Google AI"}, s)
    cfg = AgentRunConfig(time_limit_sec=20, max_model_calls=3, max_tokens_per_call=512)
    with patch("httpx.post", return_value=_fake_completion("y = 2\n")):
        result = agent.run("Write y=2", str(workspace), cfg)
    assert result.strategy == "react"
    assert result.code is not None and "y" in result.code


def test_identical_config_interface():
    """All strategies accept the same AgentRunConfig (fairness)."""
    cfg = AgentRunConfig(time_limit_sec=10, max_model_calls=2)
    s = Settings(bifrost_enabled=True)
    for aid in ("atlas-coder", "nova-coder", "forge-coder"):
        a = agent_for({"id": aid, "model": "m", "model_provider": "Google AI"}, s)
        assert hasattr(a, "run")
        # type contract
        assert a.strategy_name in ("react", "plan_act_verify", "state_machine")


def test_hidden_tests_at_least_forty():
    assert len(SPECS) == 100


def test_strategies_are_distinct_classes():
    from app.agents.react import AtlasCoderAgent
    from app.agents.plan_act_verify import NovaCoderAgent
    from app.agents.state_machine import ForgeCoderAgent
    import inspect
    s = Settings(bifrost_enabled=True)
    a = agent_for({"id": "atlas-coder", "model": "m", "model_provider": "Google AI"}, s)
    n = agent_for({"id": "nova-coder", "model": "m", "model_provider": "Google AI"}, s)
    f = agent_for({"id": "forge-coder", "model": "m", "model_provider": "OpenRouter"}, s)
    assert type(a) is AtlasCoderAgent and type(n) is NovaCoderAgent and type(f) is ForgeCoderAgent
    assert len({a.strategy_name, n.strategy_name, f.strategy_name}) == 3
    assert "Thought" in inspect.getsource(AtlasCoderAgent) or "trajectory" in inspect.getsource(AtlasCoderAgent).lower()
    assert "PLAN" in inspect.getsource(NovaCoderAgent) or "plan" in inspect.getsource(NovaCoderAgent)
    assert "GraphState" in inspect.getsource(ForgeCoderAgent) or "REPAIR" in inspect.getsource(ForgeCoderAgent)


def test_require_docker_fails_closed():
    from app.sandbox import grade, docker_available
    sol = "x = 1\n"
    tests = "def test_ok():\n    assert True\n"
    g = grade(sol, tests, timeout_sec=5, isolation="docker", image="bifrost/sandbox:py3.11-slim",
              network_policy="none", memory_mb=64, require_docker=True)
    if not docker_available():
        assert g.isolation_used == "unavailable"
        assert g.passed == 0
        assert g.error and ("Refusing" in g.error or "unavailable" in g.error.lower())


def test_full_catalogue_hidden_coverage():
    from app.catalog import build_catalogue
    assert len(SPECS) == 100
    _, tasks = build_catalogue()
    assert len(tasks) == 100
    assert all(h for _, h in tasks)
