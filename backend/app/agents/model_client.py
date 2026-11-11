"""Thin model client used by all agent strategies — always via Bifrost when enabled.

Never mutates module-level SYSTEM_PROMPT. System text is request-scoped via adapter.solve(..., system=).
"""
from __future__ import annotations

from typing import Any

from ..adapters import Generation, adapter_for, extract_code


class ModelClient:
    def __init__(self, agent_doc: dict, settings: Any):
        self.adapter = adapter_for(agent_doc, settings)
        self.agent_doc = agent_doc

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> Generation:
        """One chat completion with request-scoped system prompt."""
        return self.adapter.solve(
            user,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            system=system,
        )

    @staticmethod
    def extract_code(text: str | None) -> str | None:
        return extract_code(text or "")
