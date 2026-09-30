"""SQLAlchemy models registry."""

from app.db.base import Base
from app.db.models.user import User
from app.db.models.organization import Organization
from app.db.models.api_key import APIKey
from app.db.models.target_model import TargetModelConfig
from app.db.models.attack_template import AttackTemplate
from app.db.models.defense_config import DefenseConfig
from app.db.models.run import Run
from app.db.models.attack_result import AttackResult

__all__ = [
    "Base",
    "User",
    "Organization",
    "APIKey",
    "TargetModelConfig",
    "AttackTemplate",
    "DefenseConfig",
    "Run",
    "AttackResult",
]
