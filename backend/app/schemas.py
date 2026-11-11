"""Request schemas. Response documents are plain dicts shaped like frontend/src/types."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCORER_VERSIONS = {"scorer-2026.03.1"}


class MetricWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_success: float = Field(ge=0, le=1)
    correctness: float = Field(ge=0, le=1)
    efficiency: float = Field(ge=0, le=1)
    tool_usage: float = Field(ge=0, le=1)
    consistency: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _sum_to_one(self) -> "MetricWeights":
        total = sum(self.model_dump().values())
        if abs(total - 1.0) > 0.011:
            raise ValueError(f"metric weights must sum to 1.0 (got {total:.3f})")
        return self


class FairnessConfig(BaseModel):
    """The parity contract. Every field is required — an incomplete config is rejected (422)."""
    model_config = ConfigDict(extra="forbid")
    time_limit_per_task_sec: int = Field(ge=5, le=3600)
    max_tokens_per_task: int = Field(ge=256, le=1_000_000)
    repeats: int = Field(ge=1, le=10)
    isolation: Literal["docker", "subprocess", "vm"]
    container_image: str = Field(min_length=1)
    network_policy: Literal["none", "allowlist", "full"]
    randomize_task_order: bool
    random_seed: int
    scorer_version: str
    temperature: float = Field(ge=0, le=2)
    blinded_evaluation: bool
    metric_weights: MetricWeights

    @field_validator("scorer_version")
    @classmethod
    def _known_scorer(cls, v: str) -> str:
        if v not in SCORER_VERSIONS:
            raise ValueError(f"unknown scorer_version '{v}' (supported: {', '.join(sorted(SCORER_VERSIONS))})")
        return v

    @field_validator("isolation")
    @classmethod
    def _isolation_supported(cls, v: str) -> str:
        if v == "vm":
            raise ValueError("isolation 'vm' is not supported by this backend yet (use 'docker' or 'subprocess')")
        return v


class RunCreate(BaseModel):
    """Create a benchmark run.

    ``task_ids`` selects a subset of the benchmark. When omitted or empty the
    backend uses every task in the benchmark (backward-compatible default).
    When provided, every id must belong to ``benchmark_id``.
    """
    model_config = ConfigDict(extra="forbid")
    benchmark_id: str
    agent_ids: list[str] = Field(min_length=1)
    task_ids: list[str] | None = None
    fairness: FairnessConfig
    notes: str = ""
    name: str | None = None

    @field_validator("agent_ids")
    @classmethod
    def _unique_agents(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("agent_ids must not contain duplicates")
        return v

    @field_validator("task_ids")
    @classmethod
    def _unique_tasks(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if len(set(v)) != len(v):
            raise ValueError("task_ids must not contain duplicates")
        if len(v) == 0:
            raise ValueError("task_ids must not be empty when provided — omit the field to use the full benchmark")
        return v


class AgentToolIn(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""


class AgentCreate(BaseModel):
    """Partial Agent — only name, model and model_provider are required."""
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=2, max_length=60)
    model: str = Field(min_length=1)
    model_provider: str = Field(min_length=1)
    description: str = ""
    system_prompt_version: str = "sys-2.4.1"
    tools: list[AgentToolIn] | None = None
    orchestration: str = "ReAct loop (think → act → observe)"
    memory: str = "None"
    color_index: int | None = Field(default=None, ge=0, le=4)
    cost_per_1k_input: float = Field(default=0.001, ge=0)
    cost_per_1k_output: float = Field(default=0.008, ge=0)
