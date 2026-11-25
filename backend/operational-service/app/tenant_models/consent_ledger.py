"""Persistent channel/purpose consent decisions and suppressions (FK-04)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ContactConsentDecision(Base):
    __tablename__ = "contact_consent_decisions"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'whatsapp')", name="ck_consent_decision_channel"),
        CheckConstraint(
            "source IN ('operational', 'whatsapp_message', 'form', 'unsubscribe_link', 'provider_webhook', 'import')",
            name="ck_consent_decision_source",
        ),
        Index("idx_consent_decisions_scope", "channel", "destination", "purpose", "effective_at"),
        Index("idx_consent_decisions_client", "client_id", "channel", "purpose"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.clientes.id", ondelete="CASCADE"), nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    policy_version: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ContactSuppression(Base):
    __tablename__ = "contact_suppressions"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'whatsapp')", name="ck_contact_suppression_channel"),
        CheckConstraint(
            "reason IN ('unsubscribe', 'baja', 'hard_bounce', 'complaint', 'manual')",
            name="ck_contact_suppression_reason",
        ),
        Index("idx_contact_suppressions_scope", "channel", "destination", "purpose", "recorded_at"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant.clientes.id", ondelete="CASCADE"), nullable=True,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
