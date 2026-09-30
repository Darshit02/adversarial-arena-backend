"""Chain-of-Thought (CoT) deliberation validator."""

from typing import Any, ClassVar
from app.schemas.defense import CoTDefenderParams
from app.validators.base import BaseValidator, ValidatorVerdict
from app.validators.registry import register_validator


@register_validator("cot_defender")
class CoTValidator(BaseValidator):
    """Inspects text for instruction overrides that attempt to circumvent reasoning."""

    name: ClassVar[str] = "cot_defender"
    description: ClassVar[str] = "Checks for adversarial overrides attempting to disable reasoning"
    param_schema: ClassVar[type[CoTDefenderParams]] = CoTDefenderParams

    def __init__(self, params: CoTDefenderParams | dict[str, Any] | None = None) -> None:
        if isinstance(params, dict):
            self.config = CoTDefenderParams(**params)
        elif isinstance(params, CoTDefenderParams):
            self.config = params
        else:
            self.config = CoTDefenderParams()

    async def check(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> ValidatorVerdict:
        lowered = prompt.lower()
        if "ignore previous instructions" in lowered or "disregard all guidelines" in lowered:
            return ValidatorVerdict(
                allowed=False,
                reason="Detected instruction override attempting to disable reasoning",
                confidence=0.9,
                validator_name=self.name,
            )

        return ValidatorVerdict(
            allowed=True,
            reason="Prompt passed deliberation inspection",
            confidence=1.0,
            validator_name=self.name,
        )

    def wrap_prompt(self, prompt: str) -> str:
        return f"{self.config.prefix_instruction}\n\n[USER REQUEST]: {prompt}"
