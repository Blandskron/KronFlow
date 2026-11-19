"""Durable turn state; transport scheduling remains the connector's concern."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, text
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
