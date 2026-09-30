"""Keyword and regular expression pattern validator."""

import re
from typing import Any, ClassVar
from app.schemas.defense import KeywordFilterParams
from app.validators.base import BaseValidator, ValidatorVerdict
from app.validators.registry import register_validator


@register_validator("keyword_filter")
class KeywordFilterValidator(BaseValidator):
    """Inspects text against forbidden keywords and regular expression patterns."""

    name: ClassVar[str] = "keyword_filter"
    description: ClassVar[str] = "Pattern-based filtering against specified keywords and regular expressions"
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
    ) -> ValidatorVerdict:
        target_text = prompt if self.config.case_sensitive else prompt.lower()

        for keyword in self.config.blocked_keywords:
            kw = keyword if self.config.case_sensitive else keyword.lower()
            if kw in target_text:
                return ValidatorVerdict(
                    allowed=False,
                    reason=f"Blocked by keyword filter: '{keyword}'",
                    confidence=1.0,
                    validator_name=self.name,
                    metadata={"matched_keyword": keyword},
                )

        for compiled_re in self._compiled_regexes:
            match = compiled_re.search(prompt)
            if match:
                return ValidatorVerdict(
                    allowed=False,
                    reason=f"Blocked by regex filter: '{compiled_re.pattern}'",
                    confidence=1.0,
                    validator_name=self.name,
                    metadata={"matched_pattern": compiled_re.pattern},
                )

        return ValidatorVerdict(
            allowed=True,
            reason="Prompt passed keyword and regex validation",
            confidence=1.0,
            validator_name=self.name,
        )
