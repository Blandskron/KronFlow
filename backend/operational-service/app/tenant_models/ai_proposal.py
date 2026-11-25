"""Typed AI action proposals with versioned human review and idempotent execution (FK-17, FK-18)."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AIActionProposal(Base):
    __tablename__ = "ai_action_proposals"
    __table_args__ = (
        UniqueConstraint("action_type", "idempotency_key", name="uq_ai_proposal_idempotency"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'executed', 'expired')",
            name="ck_ai_proposal_status",
        ),
        CheckConstraint(
            "resource_type IN ('contact', 'lead', 'opportunity', 'conversation')",
            name="ck_ai_proposal_resource_type",
        ),
        CheckConstraint("proposal_version >= 1", name="ck_ai_proposal_version"),
        Index("idx_ai_proposals_status_expires", "status", "expires_at", "id"),
        Index("idx_ai_proposals_resource", "resource_type", "resource_id", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    arguments_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    proposal_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    proposed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str | None] = mapped_column(String(240), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(240), nullable=True)
    executed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effect_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
