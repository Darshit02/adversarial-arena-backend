"""Pluggable defenses module and auto-discovery."""

from app.defenses.base import BaseDefense, DefenseVerdict
from app.defenses.cot_defender import CoTDefender
from app.defenses.keyword_filter import KeywordFilterDefense
from app.defenses.llm_judge import LLMJudgeDefense
from app.defenses.registry import (
    get_defense_class,
    list_registered_defenses,
    register_defense,
)

__all__ = [
    "BaseDefense",
    "DefenseVerdict",
    "register_defense",
    "get_defense_class",
    "list_registered_defenses",
    "KeywordFilterDefense",
    "LLMJudgeDefense",
    "CoTDefender",
]
