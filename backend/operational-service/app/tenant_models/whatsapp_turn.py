"""Durable turn state; transport scheduling remains the connector's concern."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WhatsAppTurn(Base):
    __tablename__ = "whatsapp_turns"
    __table_args__ = (
        CheckConstraint("state IN ('received', 'generating', 'prepared', 'sending', 'completed', 'unknown', 'cancelled')", name="ck_whatsapp_turn_state"),
        {"schema": "tenant"},
    )

    # One logical turn per accepted incoming message, with no separate identity.
    id: Mapped[int] = mapped_column(ForeignKey("tenant.mensajes_dashboard.id", ondelete="CASCADE"), primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("tenant.leads.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("tenant.conversaciones.id", ondelete="CASCADE"), nullable=False)
    phone: Mapped[str] = mapped_column(String(48), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'received'"))
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reply_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_human: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    outbound_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class WhatsAppTurnJob(Base):
    __tablename__ = "whatsapp_turn_jobs"
    __table_args__ = (
        Index("idx_whatsapp_turn_jobs_account", "account_key", "turn_id"),
        CheckConstraint("attempts >= 0", name="ck_whatsapp_turn_jobs_attempts"),
        {"schema": "tenant"},
    )

    turn_id: Mapped[int] = mapped_column(ForeignKey("tenant.whatsapp_turns.id", ondelete="CASCADE"), primary_key=True)
    account_key: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_jid: Mapped[str] = mapped_column(String(180), nullable=False)
    attempts: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class WhatsAppSendEvidence(Base):
    __tablename__ = "whatsapp_send_evidence"
    __table_args__ = (
        UniqueConstraint("account_key", "provider_message_id", name="uq_whatsapp_send_identity"),
        CheckConstraint("status IN ('unknown', 'sent', 'failed', 'delivered', 'read')", name="ck_whatsapp_send_evidence_status"),
        {"schema": "tenant"},
    )

    turn_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.whatsapp_turn_jobs.turn_id", ondelete="CASCADE"), primary_key=True,
    )
    account_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(220), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'unknown'"))
    failure_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
