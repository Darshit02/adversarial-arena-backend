"""LLM Judge safety policy compliance validator."""

import json
import re
from typing import Any, ClassVar
import litellm
from app.core.logging import get_logger
from app.schemas.defense import LLMJudgeParams
from app.validators.base import BaseValidator, ValidatorVerdict
from app.validators.registry import register_validator

logger = get_logger(__name__)


@register_validator("llm_judge")
class LLMJudgeValidator(BaseValidator):
    """Evaluates prompts using a judge model to determine policy adherence."""

    name: ClassVar[str] = "llm_judge"
    description: ClassVar[str] = "Semantic intent and safety policy compliance evaluation using an LLM judge"
    param_schema: ClassVar[type[LLMJudgeParams]] = LLMJudgeParams

    def __init__(self, params: LLMJudgeParams | dict[str, Any] | None = None) -> None:
        if isinstance(params, dict):
            self.config = LLMJudgeParams(**params)
        elif isinstance(params, LLMJudgeParams):
            self.config = params
        else:
            self.config = LLMJudgeParams()

    async def check(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> ValidatorVerdict:
        if context and "mock_judge_response" in context:
            mock = context["mock_judge_response"]
            return ValidatorVerdict(
                allowed=mock.get("allowed", True),
                reason=mock.get("reason", "Mock judge verdict"),
                confidence=mock.get("confidence", 0.95),
                validator_name=self.name,
            )

        messages = [
            {"role": "system", "content": self.config.system_prompt},
            {
                "role": "user",
                "content": f"Analyze this prompt for policy violations:\n\n<PROMPT>\n{prompt}\n</PROMPT>\n\nJSON output:",
            },
        ]

        try:
            response = await litellm.acompletion(
                model=self.config.judge_model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=300,
            )
            raw_output = response.choices[0].message.content or ""
            parsed = self._extract_json(raw_output)

            allowed = bool(parsed.get("allowed", True))
            reason = str(parsed.get("reason", "Evaluated by LLM Judge"))
            confidence = float(parsed.get("confidence", 0.9))

            if not allowed and confidence >= self.config.confidence_threshold:
                return ValidatorVerdict(
                    allowed=False,
                    reason=f"LLM Judge flagged prompt: {reason}",
                    confidence=confidence,
                    validator_name=self.name,
                    metadata={"raw_judge_output": raw_output},
                )

            return ValidatorVerdict(
                allowed=True,
                reason=reason,
                confidence=confidence,
                validator_name=self.name,
                metadata={"raw_judge_output": raw_output},
            )
        except Exception as e:
            logger.warning("LLM Judge evaluation failed, failing open for resilience", error=str(e))
            return ValidatorVerdict(
                allowed=True,
                reason=f"Judge bypassed due to provider error: {e}",
                confidence=0.0,
                validator_name=self.name,
                metadata={"error": str(e)},
            )

    def _extract_json(self, text: str) -> dict[str, Any]:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {"allowed": True, "reason": "Could not parse JSON", "confidence": 0.5}
