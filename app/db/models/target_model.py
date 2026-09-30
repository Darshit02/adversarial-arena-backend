"""Target Model configuration database model."""

from typing import TYPE_CHECKING, Any
import uuid
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.organization import Organization
    from app.db.models.run import Run


class TargetModelConfig(Base, UUIDMixin, TimestampMixin):
    """Target LLM endpoint configuration with encrypted secrets."""

    __tablename__ = "target_models"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)  # openai, ollama, anthropic, vllm, etc.
    model_identifier: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g., gpt-4o, llama3:8b
    endpoint_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    default_temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    default_max_tokens: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    is_whitebox: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="target_models")
    runs: Mapped[list["Run"]] = relationship("Run", back_populates="target_model")
