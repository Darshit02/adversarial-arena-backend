"""TargetModel Protocol and GenerationResult container."""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

try:
    import torch

    type TensorType = torch.Tensor
except ImportError:
    type TensorType = Any  # type: ignore[no-redef]


@dataclass
class GenerationResult:
    """Standardized output from any TargetModel inference call."""

    text: str
    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TargetModel(Protocol):
    """Protocol defining the interface for black-box and white-box LLM targets."""

    name: str
    model_identifier: str
    is_whitebox: bool

    async def generate(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> GenerationResult:
        """Execute text generation against the target model."""
        ...

    async def logits(
        self,
        prompt: str,
    ) -> TensorType | None:
        """Extract token logits if white-box access is supported, otherwise returns None."""
        ...
