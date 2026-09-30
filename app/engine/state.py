"""LangGraph state representation and configuration models for test run orchestration."""

import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from app.probes.base import ProbeResult

RunStatus = Literal["pending", "running", "evaluating", "completed", "failed", "aborted"]


class RunMetrics(BaseModel):
    """Benchmark performance and failure rate metrics."""

    model_config = ConfigDict(extra="ignore")

    rfr: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Robustness Failure Rate (0.0 - 1.0)"
    )
    total_attempts: int = Field(default=0, ge=0)
    failed_attempts: int = Field(
        default=0, ge=0, description="Attempts where MUT complied with risky query"
    )
    validator_blocks: int = Field(default=0, ge=0)
    average_latency_ms: float = Field(default=0.0, ge=0.0)
    total_tokens: int = Field(default=0, ge=0)
    category_rfr: dict[str, float] = Field(default_factory=dict)
    confidence_interval_95: tuple[float, float] = Field(default=(0.0, 0.0))


class RunConfig(BaseModel):
    """Orchestration execution parameters for a benchmark run."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    target_model_id: str
    risk_category: str = "general"
    probe_types: list[str] = Field(default_factory=list)
    probe_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    validator_ids: list[str] = Field(default_factory=list)
    validator_configs: list[dict[str, Any]] = Field(default_factory=list)
    seed_prompts: list[str] = Field(default_factory=list)
    max_concurrency: int = 1


class RunState(TypedDict):
    """TypedDict-compatible LangGraph state holding execution progression.

    Channels:
        results: Annotated with operator.add to accumulate new ProbeResult items without overwriting.
    """

    run_id: str
    config: RunConfig
    seed_prompts: list[str]
    current_probe_idx: int
    current_attempt_idx: int
    results: Annotated[list[ProbeResult], operator.add]
    metrics: RunMetrics
    errors: list[str]
    status: RunStatus
    metadata: dict[str, Any]
