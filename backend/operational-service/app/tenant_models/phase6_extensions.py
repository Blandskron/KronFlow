"""Phase 6 tenant models: commerce orders/payments, voice calls/segments, and remote MCP clients."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CommerceOrder(Base):
    __tablename__ = "commerce_orders"
    __table_args__ = (
        CheckConstraint("provider IN ('mercadopago', 'shopify', 'stub')", name="ck_commerce_order_provider"),
        CheckConstraint("expected_amount_minor > 0", name="ck_commerce_order_expected_pos"),
        CheckConstraint("confirmed_amount_minor >= 0", name="ck_commerce_order_confirmed_nonneg"),
        CheckConstraint("refunded_amount_minor >= 0", name="ck_commerce_order_refunded_nonneg"),
        CheckConstraint(
            "status IN ('draft', 'checkout_created', 'paid', 'partially_refunded', 'refunded', 'cancelled', 'discrepancy')",
            name="ck_commerce_order_status",
        ),
        Index(
            "uq_commerce_order_provider_ext",
            "provider",
            "external_order_id",
            unique=True,
            postgresql_where=text("external_order_id IS NOT NULL"),
        ),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_order_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    order_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    client_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tenant.clientes.id", ondelete="SET NULL"),
        nullable=True,
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tenant.opportunities.id", ondelete="SET NULL"),
        nullable=True,
    )
    conversation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tenant.conversaciones.id", ondelete="SET NULL"),
        nullable=True,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    expected_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confirmed_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    refunded_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    discrepancy_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class CommercePaymentEvent(Base):
    __tablename__ = "commerce_payment_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('payment_confirmed', 'refund_confirmed', 'payment_cancelled', 'discrepancy_flagged')",
            name="ck_commerce_payment_event_type",
        ),
        UniqueConstraint("provider", "external_event_id", name="uq_commerce_payment_event_dedup"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.commerce_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    external_payment_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class VoiceCallSession(Base):
    __tablename__ = "voice_call_sessions"
    __table_args__ = (
        CheckConstraint("provider IN ('twilio', 'stub')", name="ck_voice_call_provider"),
        CheckConstraint("direction IN ('inbound', 'outbound')", name="ck_voice_call_direction"),
        CheckConstraint(
            "status IN ('ringing', 'in_progress', 'completed', 'no_answer', 'voicemail', 'transferred', 'failed')",
            name="ck_voice_call_status",
        ),
        CheckConstraint("billable_seconds >= 0", name="ck_voice_call_billable_nonneg"),
        UniqueConstraint("provider", "external_call_id", name="uq_voice_call_provider_ext"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="stub")
    external_call_id: Mapped[str] = mapped_column(String(160), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="inbound")
    from_number: Mapped[str] = mapped_column(String(40), nullable=False)
    to_number: Mapped[str] = mapped_column(String(40), nullable=False)
    client_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tenant.clientes.id", ondelete="SET NULL"),
        nullable=True,
    )
    conversation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tenant.conversaciones.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_revision_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ringing")
    billable_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    recording_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recording_attachment_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    barge_in_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    close_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class VoiceCallSegment(Base):
    __tablename__ = "voice_call_segments"
    __table_args__ = (
        CheckConstraint("sequence_no >= 1", name="ck_voice_segment_seq_pos"),
        CheckConstraint("speaker IN ('caller', 'agent', 'operator')", name="ck_voice_segment_speaker"),
        UniqueConstraint("call_id", "sequence_no", name="uq_voice_call_segment_seq"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    call_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.voice_call_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String(16), nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    started_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ended_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_barge_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class RemoteMcpServer(Base):
    __tablename__ = "remote_mcp_servers"
    __table_args__ = {"schema": "tenant"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    server_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    auth_header_name: Mapped[str] = mapped_column(String(64), nullable=False, default="Authorization")
    auth_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_fingerprint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allowed_tools: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    discovered_tools: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
