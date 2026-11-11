"""Stage 2 — real multi-strategy AI coding agents.

Strategies (genuinely different control flows, not prompt-only):
  - AtlasCoderAgent  : ReAct (Think → Act → Observe loop)
  - NovaCoderAgent   : Plan → Act → Verify (with repair)
  - ForgeCoderAgent  : Explicit state machine (plan/code/test/repair/finish)

All agents share the same task interface and tool surface so benchmarks stay fair.
Model traffic still goes through Maxim AI Bifrost (Stage 1).
"""
from __future__ import annotations

from .base import AgentResult, AgentRunConfig, BaseAgent
from .react import AtlasCoderAgent
from .plan_act_verify import NovaCoderAgent
from .state_machine import ForgeCoderAgent


def agent_for(agent_doc: dict, settings) -> BaseAgent:
    """Factory: map catalogue agent id / orchestration hint → concrete strategy."""
    aid = (agent_doc.get("id") or "").lower()
    orch = (agent_doc.get("orchestration") or "").lower()
    if aid == "atlas-coder" or "react" in orch:
        return AtlasCoderAgent(agent_doc, settings)
    if aid == "nova-coder" or "plan" in orch and "verify" in orch:
        return NovaCoderAgent(agent_doc, settings)
    if aid == "forge-coder" or "langgraph" in orch or "state" in orch:
        return ForgeCoderAgent(agent_doc, settings)
    # Default: ReAct
    return AtlasCoderAgent(agent_doc, settings)


__all__ = [
    "AgentResult",
    "AgentRunConfig",
    "BaseAgent",
    "AtlasCoderAgent",
    "NovaCoderAgent",
    "ForgeCoderAgent",
    "agent_for",
]
