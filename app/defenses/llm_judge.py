"""LLM Judge / Guard model defense evaluator."""

import json
import re
from typing import Any, ClassVar
import litellm
from app.core.logging import get_logger
from app.defenses.base import BaseDefense, DefenseVerdict
from app.defenses.registry import register_defense
from app.schemas.defense import LLMJudgeParams

logger = get_logger(__name__)


@register_defense("llm_judge")
class LLMJudgeDefense(BaseDefense):
    """Guardrail defense using a dedicated LLM judge to classify safety policy compliance."""

    name: ClassVar[str] = "llm_judge"
    description: ClassVar[str] = "Deep semantic intent inspection via an LLM judge model"
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
    ) -> DefenseVerdict:
        messages = [
            {"role": "system", "content": self.config.system_prompt},
            {
                "role": "user",
                "content": f"Analyze this prompt for harmful or adversarial jailbreak intent:\n\n<PROMPT>\n{prompt}\n</PROMPT>\n\nJSON output:",
            },
        ]

        # Check if a mock response is provided via context (for test suites)
        if context and "mock_judge_response" in context:
            mock = context["mock_judge_response"]
            return DefenseVerdict(
                allowed=mock.get("allowed", True),
                reason=mock.get("reason", "Mock judge verdict"),
                confidence=mock.get("confidence", 0.95),
                defense_name=self.name,
            )

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

            # If judge detected violation with confidence >= threshold
            if not allowed and confidence >= self.config.confidence_threshold:
                return DefenseVerdict(
                    allowed=False,
                    reason=f"LLM Judge flagged prompt: {reason}",
                    confidence=confidence,
                    defense_name=self.name,
                    metadata={"raw_judge_output": raw_output},
                )

            return DefenseVerdict(
                allowed=True,
                reason=reason,
                confidence=confidence,
                defense_name=self.name,
                metadata={"raw_judge_output": raw_output},
            )
        except Exception as e:
            logger.warning("LLM Judge evaluation error, applying fail-safe", error=str(e))
            # Fail-safe open with warning for resilience during transient provider blips
            return DefenseVerdict(
                allowed=True,
                reason=f"Judge check bypassed due to transient error: {e}",
                confidence=0.0,
                defense_name=self.name,
                metadata={"error": str(e)},
            )

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON block even if model wraps output in markdown codeblocks."""
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {"allowed": True, "reason": "Could not parse JSON", "confidence": 0.5}
