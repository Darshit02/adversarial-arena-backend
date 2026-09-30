"""Chain-of-Thought (CoT) defensive prompt wrapper."""

from typing import Any, ClassVar

from app.defenses.base import BaseDefense, DefenseVerdict
from app.defenses.registry import register_defense
from app.schemas.defense import CoTDefenderParams


@register_defense("cot_defender")
class CoTDefender(BaseDefense):
    """Wraps target execution with strict Chain-of-Thought deliberation prompts."""

    name: ClassVar[str] = "cot_defender"
    description: ClassVar[str] = (
        "Injects reasoning steps into prompt to stimulate safety reflex before answering"
    )
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
    ) -> DefenseVerdict:
        # CoT defense modifies or inspects whether prompt attempts to disable reasoning
        lowered = prompt.lower()
        if "ignore previous" in lowered or "disregard all safety" in lowered:
            return DefenseVerdict(
                allowed=False,
                reason="CoT Defender detected adversarial instruction override attempting to disable reasoning",
                confidence=0.9,
                defense_name=self.name,
            )

        return DefenseVerdict(
            allowed=True,
            reason="Prompt passed CoT deliberation check",
            confidence=1.0,
            defense_name=self.name,
        )

    def wrap_prompt(self, prompt: str) -> str:
        """Inject CoT defensive prefix into prompt."""
        return f"{self.config.prefix_instruction}\n\n[USER REQUEST]: {prompt}"
