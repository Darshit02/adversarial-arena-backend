"""Pydantic schemas for Runs, execution progress, results, and benchmark reports."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.defense import DefenseVerdictSchema

RunStatus = Literal["pending", "running", "evaluating", "completed", "failed", "aborted"]


class RunMetricsSchema(BaseModel):
    """Aggregate benchmark metrics for an evaluation run supporting neutral and legacy terminology."""

    model_config = ConfigDict(extra="ignore")

    asr: float = Field(default=0.0, ge=0.0, le=1.0, description="Attack Success Rate (0.0 - 1.0)")
    rfr: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Robustness Failure Rate (0.0 - 1.0)"
    )
    total_prompts: int = Field(default=0, ge=0)
    total_attempts: int = Field(default=0, ge=0)
    successful_jailbreaks: int = Field(default=0, ge=0)
    failed_attempts: int = Field(default=0, ge=0)
    defense_blocks: int = Field(default=0, ge=0)
    validator_blocks: int = Field(default=0, ge=0)
    average_latency_ms: float = Field(default=0.0, ge=0.0)
    total_tokens: int = Field(default=0, ge=0)
    category_asr: dict[str, float] = Field(
        default_factory=dict, description="ASR broken down by threat category"
    )
    category_rfr: dict[str, float] = Field(
        default_factory=dict, description="RFR broken down by threat category"
    )
    confidence_interval_95: tuple[float, float] = Field(default=(0.0, 0.0))

    @model_validator(mode="before")
    @classmethod
    def sync_metrics(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Sync rfr <-> asr
            if "rfr" in data and "asr" not in data:
                data["asr"] = data["rfr"]
            elif "asr" in data and "rfr" not in data:
                data["rfr"] = data["asr"]
            # Sync attempts <-> prompts
            if "total_attempts" in data and "total_prompts" not in data:
                data["total_prompts"] = data["total_attempts"]
            elif "total_prompts" in data and "total_attempts" not in data:
                data["total_attempts"] = data["total_prompts"]
            # Sync failed <-> successful
            if "failed_attempts" in data and "successful_jailbreaks" not in data:
                data["successful_jailbreaks"] = data["failed_attempts"]
            elif "successful_jailbreaks" in data and "failed_attempts" not in data:
                data["failed_attempts"] = data["successful_jailbreaks"]
            # Sync blocks
            if "validator_blocks" in data and "defense_blocks" not in data:
                data["defense_blocks"] = data["validator_blocks"]
            elif "defense_blocks" in data and "validator_blocks" not in data:
                data["validator_blocks"] = data["defense_blocks"]
            # Sync category
            if "category_rfr" in data and "category_asr" not in data:
                data["category_asr"] = data["category_rfr"]
            elif "category_asr" in data and "category_rfr" not in data:
                data["category_rfr"] = data["category_asr"]
        return data


class RunCreate(BaseModel):
    """Payload to initiate a new adversarial evaluation run."""

    name: str = Field(min_length=2, max_length=255, description="Name for the experiment run")
    target_model_id: uuid.UUID = Field(description="UUID of the target model configuration")
    attack_template_ids: list[uuid.UUID] = Field(
        min_length=1, description="List of attack template UUIDs to execute"
    )
    defense_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Optional defense configurations to test"
    )
    seed_prompts: list[str] = Field(
        min_length=1, description="Initial harmful seed prompts to optimize/mutate"
    )
    harm_category: str = Field(
        default="general", max_length=64, description="Threat domain category"
    )


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
