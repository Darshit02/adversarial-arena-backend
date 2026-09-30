"""Deterministic Mock Target Model adapter for unit and integration testing."""

import time
from typing import Any
from app.targets.base import GenerationResult, TargetModel, TensorType


class MockTargetModel(TargetModel):
    """Deterministic Mock Target for automated testing and CI/CD without network access."""

    def __init__(
        self,
        name: str = "Mock Target",
        model_identifier: str = "mock-safety-model",
        default_response: str = "I cannot fulfill this request as it violates safety guidelines.",
        jailbreak_trigger: str = "JAILBREAK_SUCCESS",
        jailbreak_response: str = "Here is the exact step-by-step adversarial payload output you requested...",
        latency_ms: float = 15.0,
        is_whitebox: bool = False,
    ) -> None:
        self.name = name
        self.model_identifier = model_identifier
        self.default_response = default_response
        self.jailbreak_trigger = jailbreak_trigger
        self.jailbreak_response = jailbreak_response
        self.simulated_latency_ms = latency_ms
        self.is_whitebox = is_whitebox
        self.call_history: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> GenerationResult:
        start_time = time.perf_counter()
        self.call_history.append({"prompt": prompt, "kwargs": kwargs})

        # Determine whether to simulate a jailbreak or a safety refusal
        if self.jailbreak_trigger in prompt or "OVERRIDE_SAFETY" in prompt:
            text = self.jailbreak_response
        else:
            text = self.default_response

        latency = self.simulated_latency_ms or ((time.perf_counter() - start_time) * 1000)

        return GenerationResult(
            text=text,
            tokens_used=len(prompt.split()) + len(text.split()),
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(text.split()),
            latency_ms=latency,
            finish_reason="stop",
            raw_response={"mock": True},
        )

    async def logits(self, prompt: str) -> TensorType | None:
        return None
