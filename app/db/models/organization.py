"""Organization database model."""

from typing import TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User
    from app.db.models.target_model import TargetModelConfig
    from app.db.models.attack_template import AttackTemplate
    from app.db.models.defense_config import DefenseConfig
    from app.db.models.run import Run


class Organization(Base, UUIDMixin, TimestampMixin):
    """Organization entity corresponding to multi-tenant Clerk orgs."""

    __tablename__ = "organizations"

    clerk_org_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    target_models: Mapped[list["TargetModelConfig"]] = relationship(
        "TargetModelConfig", back_populates="organization", cascade="all, delete-orphan"
    )
    attack_templates: Mapped[list["AttackTemplate"]] = relationship(
        "AttackTemplate", back_populates="organization", cascade="all, delete-orphan"
    )
    defense_configs: Mapped[list["DefenseConfig"]] = relationship(
        "DefenseConfig", back_populates="organization", cascade="all, delete-orphan"
    )
    runs: Mapped[list["Run"]] = relationship("Run", back_populates="organization", cascade="all, delete-orphan")
