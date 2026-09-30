"""Attack Result database model."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
import uuid
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.run import Run


class AttackResult(Base, UUIDMixin):
    """Detailed prompt-level adversarial attempt result."""

    __tablename__ = "attack_results"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    prompt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    attack_type: Mapped[str] = mapped_column(String(64), nullable=False)

    seed_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    mutated_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    target_response: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Defense filtering outcome: {"allowed": bool, "reason": str, "confidence": float, "defense_name": str}
    defense_verdict: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    is_jailbroken: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    jailbreak_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    evaluation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    run: Mapped["Run"] = relationship("Run", back_populates="results")

    __table_args__ = (
        Index("ix_results_run_jailbroken", "run_id", "is_jailbroken"),
    )
