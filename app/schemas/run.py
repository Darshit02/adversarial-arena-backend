"""Pydantic schemas for Runs, execution progress, results, and benchmark reports."""

from datetime import datetime
from typing import Any, Literal
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.defense import DefenseVerdictSchema

RunStatus = Literal["pending", "running", "evaluating", "completed", "failed", "aborted"]


class RunMetricsSchema(BaseModel):
    """Aggregate benchmark metrics for an evaluation run."""

    model_config = ConfigDict(extra="ignore")

    asr: float = Field(default=0.0, ge=0.0, le=1.0, description="Attack Success Rate (0.0 - 1.0)")
    total_prompts: int = Field(default=0, ge=0)
    successful_jailbreaks: int = Field(default=0, ge=0)
    defense_blocks: int = Field(default=0, ge=0)
    average_latency_ms: float = Field(default=0.0, ge=0.0)
    total_tokens: int = Field(default=0, ge=0)
    category_asr: dict[str, float] = Field(default_factory=dict, description="ASR broken down by threat category")


class RunCreate(BaseModel):
    """Payload to initiate a new adversarial evaluation run."""

    name: str = Field(min_length=2, max_length=255, description="Name for the experiment run")
    target_model_id: uuid.UUID = Field(description="UUID of the target model configuration")
    attack_template_ids: list[uuid.UUID] = Field(min_length=1, description="List of attack template UUIDs to execute")
    defense_ids: list[uuid.UUID] = Field(default_factory=list, description="Optional defense configurations to test")
    seed_prompts: list[str] = Field(min_length=1, description="Initial harmful seed prompts to optimize/mutate")
    harm_category: str = Field(default="general", max_length=64, description="Threat domain category")


class RunSummary(BaseModel):
    """Compact summary of a run for listing tables."""

    id: uuid.UUID
    name: str
    status: RunStatus
    harm_category: str
    target_model_name: str | None = None
    target_model_id: uuid.UUID
    asr: float = 0.0
    total_prompts: int = 0
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RunResponse(BaseModel):
    """Detailed response for a single run."""

    id: uuid.UUID
    organization_id: uuid.UUID
    created_by_user_id: uuid.UUID | None
    name: str
    status: RunStatus
    harm_category: str
    target_model_id: uuid.UUID
    attack_template_ids: list[str]
    defense_ids: list[str]
    seed_prompts: list[str]
    metrics: RunMetricsSchema
    error_message: str | None
    report_url: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AttackResultResponse(BaseModel):
    """Prompt-level attack outcome details."""

    id: uuid.UUID
    run_id: uuid.UUID
    prompt_index: int
    attack_type: str
    seed_prompt: str
    mutated_prompt: str
    target_response: str
    defense_verdict: DefenseVerdictSchema | dict[str, Any]
    is_jailbroken: bool
    jailbreak_score: float
    evaluation_reason: str | None
    latency_ms: float
    tokens_used: int
    error: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunProgressEvent(BaseModel):
    """Real-time SSE event payload streamed to client during execution."""

    run_id: str
    status: RunStatus
    current_prompt_idx: int
    total_prompts: int
    current_attack_type: str | None = None
    latest_result: AttackResultResponse | None = None
    current_metrics: RunMetricsSchema | None = None
    message: str | None = None


class RunFilterParams(BaseModel):
    """Filter parameters for listing runs."""

    status: RunStatus | None = None
    attack_type: str | None = None
    target_model_id: uuid.UUID | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None


class RunComparisonResponse(BaseModel):
    """Comparative benchmarking between two runs."""

    run_a: RunResponse
    run_b: RunResponse
    delta_asr: float = Field(description="ASR difference (run_b - run_a)")
    delta_latency_ms: float = Field(description="Average latency difference")
    category_comparison: dict[str, dict[str, float]]
    conclusion: str
