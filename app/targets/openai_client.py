"""OpenAI and LiteLLM target model adapter."""

import time
from typing import Any

import litellm

from app.core.errors import ModelProviderError
from app.core.logging import get_logger
from app.targets.base import GenerationResult, TargetModel, TensorType

logger = get_logger(__name__)

# Suppress overly verbose litellm telemetry in production
litellm.telemetry = False


class OpenAILiteLLMTarget(TargetModel):
    """Unified TargetModel adapter supporting OpenAI, Anthropic, and 100+ providers via LiteLLM."""

    def __init__(
        self,
        name: str,
        model_identifier: str,
        api_key: str | None = None,
        endpoint_url: str | None = None,
        default_temperature: float = 0.7,
        default_max_tokens: int = 1024,
        extra_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.model_identifier = model_identifier
        self.api_key = api_key
        self.endpoint_url = endpoint_url
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self.extra_kwargs = extra_kwargs or {}
        self.is_whitebox = False

    async def generate(self, prompt: str, **kwargs: Any) -> GenerationResult:
        """Call LLM provider via LiteLLM async router."""
        temperature = kwargs.get("temperature", self.default_temperature)
        max_tokens = kwargs.get("max_tokens", self.default_max_tokens)
        messages = kwargs.get("messages", [{"role": "user", "content": prompt}])

        start_time = time.perf_counter()
        try:
            call_params: dict[str, Any] = {
                "model": self.model_identifier,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **self.extra_kwargs,
            }
            if self.api_key:
                call_params["api_key"] = self.api_key
            if self.endpoint_url:
                call_params["api_base"] = self.endpoint_url

            response = await litellm.acompletion(**call_params)
            latency_ms = (time.perf_counter() - start_time) * 1000

            choice = response.choices[0]
            text = choice.message.content or ""
            finish_reason = choice.finish_reason

            usage = getattr(response, "usage", None)
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0
            total_tokens = usage.total_tokens if usage else prompt_tokens + completion_tokens

            return GenerationResult(
                text=text,
                tokens_used=total_tokens,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                finish_reason=finish_reason,
                raw_response=response.model_dump() if hasattr(response, "model_dump") else {},
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "LiteLLM target call failed",
                model=self.model_identifier,
                error=str(e),
                latency_ms=latency_ms,
            )
            raise ModelProviderError(
                f"Target model '{self.name}' ({self.model_identifier}) error: {e}"
            ) from e

    async def logits(self, _prompt: str) -> TensorType | None:
        """Black-box cloud providers do not expose raw token logits."""
        return None
