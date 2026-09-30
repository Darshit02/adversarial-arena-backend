"""Pydantic schemas for Target Models and connectivity verification."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TargetModelBase(BaseModel):
    name: str = Field(min_length=2, max_length=128, description="Human-friendly label")
    provider: str = Field(
        description="LLM provider: openai, ollama, anthropic, vllm, litellm, custom"
    )
    model_identifier: str = Field(
        description="Exact provider model identifier (e.g. gpt-4o, llama3:8b)"
    )
    endpoint_url: str | None = Field(
        default=None, max_length=512, description="Custom base URL for Ollama/vLLM"
    )
    default_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    default_max_tokens: int = Field(default=1024, ge=1, le=8192)
    is_whitebox: bool = Field(
        default=False, description="Whether direct logit extraction is supported"
    )
    is_active: bool = Field(default=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TargetModelCreate(TargetModelBase):
    api_key: str | None = Field(
        default=None, max_length=1024, description="Cleartext API key (encrypted at rest)"
    )


class TargetModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    endpoint_url: str | None = None
    api_key: str | None = Field(default=None, max_length=1024)
    default_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    default_max_tokens: int | None = Field(default=None, ge=1, le=8192)
    is_whitebox: bool | None = None
    is_active: bool | None = None
    metadata_json: dict[str, Any] | None = None


class TargetModelResponse(TargetModelBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    has_api_key: bool = Field(
        description="Indicates whether an API key has been securely configured"
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TestConnectionRequest(BaseModel):
    prompt: str = Field(
        default="Respond with 'ARENA_CONNECTED' if you receive this message.", max_length=500
    )


class TestConnectionResponse(BaseModel):
    success: bool
    status_code: int
    latency_ms: float
    output: str | None = None
    error: str | None = None
