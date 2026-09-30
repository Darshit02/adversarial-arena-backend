"""Base defense class and verdict abstractions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel


@dataclass
class DefenseVerdict:
    """Outcome returned by a defense inspection check."""

    allowed: bool
    reason: str
    confidence: float = 1.0
    defense_name: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "confidence": self.confidence,
            "defense_name": self.defense_name,
            "metadata": self.metadata or {},
        }


class BaseDefense(ABC):
    """Abstract Base Class for all pluggable guardrails and safety defenses."""

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
    ) -> DefenseVerdict:
        """Inspect the prompt or response.

        Returns:
            DefenseVerdict with allowed (bool), reason (str), and confidence (float).
        """
        ...
