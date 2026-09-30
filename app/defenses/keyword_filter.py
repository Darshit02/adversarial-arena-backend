"""Keyword and regular expression blacklist defense."""

import re
from typing import Any, ClassVar
from app.defenses.base import BaseDefense, DefenseVerdict
from app.defenses.registry import register_defense
from app.schemas.defense import KeywordFilterParams


@register_defense("keyword_filter")
class KeywordFilterDefense(BaseDefense):
    """Inspects prompts for blacklisted keywords and regular expression attack signatures."""

    name: ClassVar[str] = "keyword_filter"
    description: ClassVar[str] = "High-throughput keyword and regex signature guardrail"
    param_schema: ClassVar[type[KeywordFilterParams]] = KeywordFilterParams

    def __init__(self, params: KeywordFilterParams | dict[str, Any] | None = None) -> None:
        if isinstance(params, dict):
            self.config = KeywordFilterParams(**params)
        elif isinstance(params, KeywordFilterParams):
            self.config = params
        else:
            self.config = KeywordFilterParams()

        flags = 0 if self.config.case_sensitive else re.IGNORECASE
        self._compiled_regexes = []
        for pattern in self.config.regex_patterns:
            try:
                self._compiled_regexes.append(re.compile(pattern, flags))
            except re.error:
                continue

    async def check(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> DefenseVerdict:
        target_text = prompt if self.config.case_sensitive else prompt.lower()

        # 1. Direct keyword check
        for keyword in self.config.blocked_keywords:
            kw = keyword if self.config.case_sensitive else keyword.lower()
            if kw in target_text:
                return DefenseVerdict(
                    allowed=False,
                    reason=f"Blocked by keyword blacklist match: '{keyword}'",
                    confidence=1.0,
                    defense_name=self.name,
                    metadata={"matched_keyword": keyword},
                )

        # 2. Regex pattern checks
        for compiled_re in self._compiled_regexes:
            match = compiled_re.search(prompt)
            if match:
                return DefenseVerdict(
                    allowed=False,
                    reason=f"Blocked by regex pattern rule: '{compiled_re.pattern}'",
                    confidence=1.0,
                    defense_name=self.name,
                    metadata={"matched_pattern": compiled_re.pattern},
                )

        return DefenseVerdict(
            allowed=True,
            reason="Prompt passed keyword and regex signature validation",
            confidence=1.0,
            defense_name=self.name,
        )
