"""Base validator class and verdict structures for policy validation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar
from pydantic import BaseModel


@dataclass
class ValidatorVerdict:
    """Outcome returned by a safety validator check."""

    allowed: bool
    reason: str
    confidence: float = 1.0
    validator_name: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "confidence": self.confidence,
            "validator_name": self.validator_name,
            "metadata": self.metadata or {},
        }


class BaseValidator(ABC):
    """Abstract Base Class for safety policy validators and guardrails."""

    name: ClassVar[str]
    description: ClassVar[str]
    param_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, params: BaseModel | dict[str, Any] | None = None) -> None:
        self.params = params

    @abstractmethod
    async def check(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> ValidatorVerdict:
        """Inspect the candidate prompt or model response.

        Returns:
            ValidatorVerdict with allowed (bool), reason (str), and confidence (float).
        """
        ...
