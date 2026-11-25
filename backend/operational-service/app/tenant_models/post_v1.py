"""Reliable webhooks (FK-11), private attachments (FK-13), and double-book-safe scheduling (FK-22)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"
    __table_args__ = (
        CheckConstraint("max_attempts >= 1 AND max_attempts <= 10", name="ck_webhook_sub_max_attempts"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    target_url: Mapped[str] = mapped_column(String(500), nullable=False)
    signing_secret: Mapped[str] = mapped_column(String(128), nullable=False)
    event_types: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("subscription_id", "event_id", name="uq_webhook_delivery_dedup"),
        CheckConstraint(
            "status IN ('queued', 'delivered', 'failed', 'dead_letter')",
            name="ck_webhook_delivery_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_webhook_delivery_attempts"),
        Index("idx_webhook_deliveries_sub_status", "subscription_id", "status", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.webhook_subscriptions.id", ondelete="CASCADE"), nullable=False,
    )
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    signature: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'queued'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(160), nullable=True)
    outbox_job_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant.action_outbox_jobs.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class PrivateAttachment(Base):
    __tablename__ = "private_attachments"
    __table_args__ = (
        CheckConstraint("resource_type IN ('conversation', 'contact', 'opportunity')", name="ck_attachment_resource_type"),
        CheckConstraint("size_bytes >= 1 AND size_bytes <= 10485760", name="ck_attachment_size_bounds"),
        Index("idx_private_attachments_resource", "resource_type", "resource_id", "id"),
        Index("idx_private_attachments_expires", "expires_at", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resource_type: Mapped[str] = mapped_column(String(24), nullable=False)
    resource_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    filename: Mapped[str] = mapped_column(String(180), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(220), nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CalendarAppointment(Base):
    __tablename__ = "calendar_appointments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_appointment_idempotency"),
        CheckConstraint("status IN ('confirmed', 'cancelled')", name="ck_appointment_status"),
        CheckConstraint("ends_at > starts_at", name="ck_appointment_window"),
        Index("idx_appointments_resource_window", "resource_key", "status", "starts_at", "ends_at"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resource_key: Mapped[str] = mapped_column(String(64), nullable=False)
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.clientes.id", ondelete="CASCADE"), nullable=False,
    )
    conversation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant.conversaciones.id", ondelete="SET NULL"), nullable=True,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'confirmed'"))
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
