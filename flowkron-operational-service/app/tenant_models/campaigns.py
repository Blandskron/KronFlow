"""Tenant channel connections (FK-24), templates, campaigns, and durable receipts (FK-30)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TenantChannelConnection(Base):
    __tablename__ = "tenant_channel_connections"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'whatsapp')", name="ck_channel_conn_channel"),
        CheckConstraint(
            "provider IN ('stub', 'resend', 'whatsapp_business_official')",
            name="ck_channel_conn_provider",
        ),
        CheckConstraint(
            "status IN ('active', 'revoked', 'pending_verification')",
            name="ck_channel_conn_status",
        ),
        CheckConstraint("credential_version >= 1", name="ck_channel_conn_cred_version"),
        Index("idx_channel_conn_channel_status", "channel", "status"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    sender_address: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'active'"))
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sandbox_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    secret_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class MessageTemplate(Base):
    __tablename__ = "message_templates"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'whatsapp')", name="ck_message_template_channel"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'es'"))
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class TemplateVersion(Base):
    __tablename__ = "template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_template_version"),
        CheckConstraint("version >= 1", name="ck_template_version_num"),
        CheckConstraint("status IN ('draft', 'approved', 'archived')", name="ck_template_version_status"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.message_templates.id", ondelete="CASCADE"), nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'draft'"))
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    declared_variables: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'whatsapp')", name="ck_campaign_channel"),
        CheckConstraint(
            "status IN ('draft', 'approved', 'scheduled', 'running', 'paused', 'completed', 'cancelled', 'failed')",
            name="ck_campaign_status",
        ),
        CheckConstraint("version >= 1", name="ck_campaign_version"),
        Index("idx_campaigns_status", "status", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.template_versions.id", ondelete="RESTRICT"), nullable=False,
    )
    connection_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.tenant_channel_connections.id", ondelete="RESTRICT"), nullable=False,
    )
    segment_filter: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    timezone_iana: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'UTC'"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'draft'"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CampaignApproval(Base):
    __tablename__ = "campaign_approvals"
    __table_args__ = (
        Index("idx_campaign_approvals_campaign", "campaign_id", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.campaigns.id", ondelete="CASCADE"), nullable=False,
    )
    campaign_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    connection_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    approved_by: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"
    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_point_id", name="uq_campaign_recipient_point"),
        UniqueConstraint("campaign_id", "destination", name="uq_campaign_recipient_destination"),
        CheckConstraint(
            "status IN ('queued', 'suppressed', 'accepted', 'delivered', 'bounced', 'complained', 'unsubscribed', 'unknown', 'failed')",
            name="ck_campaign_recipient_status",
        ),
        Index("idx_campaign_recipients_status", "campaign_id", "status", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.campaigns.id", ondelete="CASCADE"), nullable=False,
    )
    contact_point_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.contact_points.id", ondelete="CASCADE"), nullable=False,
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.clientes.id", ondelete="CASCADE"), nullable=False,
    )
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'queued'"))
    outbox_job_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant.action_outbox_jobs.id", ondelete="SET NULL"), nullable=True,
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(220), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        CheckConstraint("attempt_number >= 1", name="ck_delivery_attempt_num"),
        CheckConstraint("outcome IN ('accepted', 'unknown', 'failed')", name="ck_delivery_attempt_outcome"),
        Index("idx_delivery_attempts_recipient", "campaign_recipient_id", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_recipient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.campaign_recipients.id", ondelete="CASCADE"), nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(220), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ChannelEvent(Base):
    __tablename__ = "channel_events"
    __table_args__ = (
        UniqueConstraint("provider_account_id", "provider_event_id", name="uq_channel_event_identity"),
        CheckConstraint(
            "event_type IN ('accepted', 'delivered', 'bounced', 'complained', 'unsubscribed')",
            name="ck_channel_event_type",
        ),
        Index("idx_channel_events_provider_msg", "provider_message_id", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_account_id: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(180), nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(220), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
