"""Durable conversation control (HITL) state, history, and tenant AI policy (FK-06, FK-19)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConversationControl(Base):
    __tablename__ = "conversation_controls"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('ai_active', 'waiting_human', 'human_active', 'resolved')",
            name="ck_conversation_control_mode",
        ),
        CheckConstraint("control_version >= 1", name="ck_conversation_control_version"),
        {"schema": "tenant"},
    )

    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.conversaciones.id", ondelete="CASCADE"), primary_key=True,
    )
    mode: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'ai_active'"))
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    control_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    handoff_reason: Mapped[str | None] = mapped_column(String(180), nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(String(180), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ConversationControlEvent(Base):
    __tablename__ = "conversation_control_events"
    __table_args__ = (
        Index("idx_conversation_control_events_conv", "conversation_id", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.conversaciones.id", ondelete="CASCADE"), nullable=False,
    )
    from_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    to_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    control_version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class TenantAIPolicy(Base):
    __tablename__ = "tenant_ai_policies"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_tenant_ai_policy_singleton"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default=text("1"))
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(180), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
