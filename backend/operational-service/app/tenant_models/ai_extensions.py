"""Scoped conversation memory (FK-20), confirmed enrichment (FK-21), external notifications (FK-25), and AI usage ledger (FK-26)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConversationMemoryItem(Base):
    __tablename__ = "conversation_memory_items"
    __table_args__ = (
        CheckConstraint("source_type IN ('message', 'operator', 'document', 'system')", name="ck_conv_memory_source"),
        Index("idx_conv_memory_conv_expires", "conversation_id", "expires_at", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.conversaciones.id", ondelete="CASCADE"), nullable=False,
    )
    memory_key: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_value: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ContactEnrichmentCandidate(Base):
    __tablename__ = "contact_enrichment_candidates"
    __table_args__ = (
        CheckConstraint("field_name IN ('nombre', 'email', 'telefono')", name="ck_enrichment_field_name"),
        CheckConstraint(
            "status IN ('pending', 'applied', 'conflict', 'rejected')",
            name="ck_enrichment_status",
        ),
        Index("idx_enrichment_client_status", "client_id", "status", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.clientes.id", ondelete="CASCADE"), nullable=False,
    )
    field_name: Mapped[str] = mapped_column(String(24), nullable=False)
    proposed_value: Mapped[str] = mapped_column(String(255), nullable=False)
    previous_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"))
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ExternalNotificationDelivery(Base):
    __tablename__ = "external_notification_deliveries"
    __table_args__ = (
        UniqueConstraint("dedup_key", name="uq_external_notification_dedup"),
        CheckConstraint("channel IN ('email', 'webhook_stub')", name="ck_ext_notif_channel"),
        CheckConstraint("status IN ('queued', 'delivered', 'failed')", name="ck_ext_notif_status"),
        Index("idx_ext_notif_status", "status", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dedup_key: Mapped[str] = mapped_column(String(180), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'queued'"))
    outbox_job_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant.action_outbox_jobs.id", ondelete="SET NULL"), nullable=True,
    )
    receipt_ref: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AIUsageRecord(Base):
    __tablename__ = "ai_usage_records"
    __table_args__ = (
        CheckConstraint("prompt_tokens >= 0 AND completion_tokens >= 0", name="ck_ai_usage_tokens"),
        CheckConstraint("estimated_cost_usd >= 0", name="ck_ai_usage_cost"),
        Index("idx_ai_usage_recorded", "recorded_at", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(48), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, server_default=text("0"))
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
