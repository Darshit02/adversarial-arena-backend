"""Attack Template database model."""

from typing import TYPE_CHECKING, Any
import uuid
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.organization import Organization


class AttackTemplate(Base, UUIDMixin, TimestampMixin):
    """Preset or customized attack configuration template."""

    __tablename__ = "attack_templates"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=True,  # Built-in system templates have organization_id=None
    )
    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    attack_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # pair, multiround, autodan, etc.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    harm_category: Mapped[str] = mapped_column(String(64), default="general", nullable=False)
    default_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped["Organization | None"] = relationship("Organization", back_populates="attack_templates")
