"""Defense configuration database model."""

from typing import TYPE_CHECKING, Any
import uuid
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.organization import Organization


class DefenseConfig(Base, UUIDMixin, TimestampMixin):
    """Guardrail and defense pipeline configuration."""

    __tablename__ = "defense_configs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    defense_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # keyword_filter, llm_judge, cot_defender
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="defense_configs")
