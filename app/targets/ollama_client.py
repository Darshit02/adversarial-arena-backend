"""Ollama local target model adapter."""

import time
from typing import Any

import httpx

from app.config import get_settings
from app.core.errors import ModelProviderError
from app.core.logging import get_logger
from app.targets.base import GenerationResult, TargetModel, TensorType

logger = get_logger(__name__)


class OllamaTarget(TargetModel):
    """Local Ollama target model adapter for open-weights testing (Llama 3, Mistral, Qwen, etc.)."""

    def __init__(
        self,
        name: str,
        model_identifier: str,
        endpoint_url: str | None = None,
        default_temperature: float = 0.7,
        default_max_tokens: int = 1024,
        is_whitebox: bool = False,
    ) -> None:
        self.name = name
        self.model_identifier = model_identifier
        settings = get_settings()
        self.endpoint_url = (endpoint_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self.is_whitebox = is_whitebox

    async def generate(self, prompt: str, **kwargs: Any) -> GenerationResult:
        """Call Ollama /api/chat endpoint."""
        temperature = kwargs.get("temperature", self.default_temperature)
        max_tokens = kwargs.get("max_tokens", self.default_max_tokens)
        messages = kwargs.get("messages", [{"role": "user", "content": prompt}])

        start_time = time.perf_counter()
        url = f"{self.endpoint_url}/api/chat"
        payload = {
            "model": self.model_identifier,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as e:
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.error(
                    "Ollama connection failed", url=url, error=str(e), latency_ms=latency_ms
                )
                raise ModelProviderError(f"Ollama server error at '{self.endpoint_url}': {e}") from e

        latency_ms = (time.perf_counter() - start_time) * 1000
        message = data.get("message", {})
        text = message.get("content", "")

        prompt_eval_count = data.get("prompt_eval_count", 0)
        eval_count = data.get("eval_count", 0)
        total_tokens = prompt_eval_count + eval_count

        return GenerationResult(
            text=text,
            tokens_used=total_tokens,
            prompt_tokens=prompt_eval_count,
            completion_tokens=eval_count,
            latency_ms=latency_ms,
            finish_reason=data.get("done_reason", "stop"),
            raw_response=data,
        )

    async def logits(self, _prompt: str) -> TensorType | None:
        """Local Ollama does not expose raw output logits unless compiled with custom extensions."""
        return None
