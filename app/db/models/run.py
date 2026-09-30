"""Run execution database model."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
import uuid
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.organization import Organization
    from app.db.models.user import User
    from app.db.models.target_model import TargetModelConfig
    from app.db.models.attack_result import AttackResult


class Run(Base, UUIDMixin, TimestampMixin):
    """Adversarial evaluation experiment run."""

    __tablename__ = "runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    target_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("target_models.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        index=True,
        nullable=False,
    )  # pending, running, evaluating, completed, failed, aborted

    harm_category: Mapped[str] = mapped_column(String(64), default="general", nullable=False)
    seed_prompts: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    attack_template_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    defense_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    # Aggregated metrics (ASR, count, latency, tokens)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="runs")
    created_by: Mapped["User | None"] = relationship("User", back_populates="runs")
    target_model: Mapped["TargetModelConfig"] = relationship("TargetModelConfig", back_populates="runs")
    results: Mapped[list["AttackResult"]] = relationship(
        "AttackResult", back_populates="run", cascade="all, delete-orphan", order_by="AttackResult.prompt_index"
    )

    __table_args__ = (
        Index("ix_runs_org_status_created", "organization_id", "status", "created_at"),
    )
