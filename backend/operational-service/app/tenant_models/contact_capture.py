"""Persistent multichannel contact points and idempotent lead captures (FK-28)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ContactPoint(Base):
    __tablename__ = "contact_points"
    __table_args__ = (
        UniqueConstraint("point_type", "normalized_value", name="uq_contact_point_identity"),
        CheckConstraint("point_type IN ('email', 'phone', 'whatsapp')", name="ck_contact_point_type"),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_contact_point_status"),
        Index("idx_contact_points_client", "client_id", "point_type"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.clientes.id", ondelete="CASCADE"), nullable=False,
    )
    point_type: Mapped[str] = mapped_column(String(16), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'manual'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class LeadCapture(Base):
    __tablename__ = "lead_captures"
    __table_args__ = (
        UniqueConstraint("source_kind", "source_ref", "idempotency_key", name="uq_lead_capture_idempotency"),
        CheckConstraint("source_kind IN ('integration', 'public_form')", name="ck_lead_capture_source_kind"),
        CheckConstraint("status IN ('accepted', 'conflict_review')", name="ck_lead_capture_status"),
        Index("idx_lead_captures_created", "created_at", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant.clientes.id", ondelete="SET NULL"), nullable=True,
    )
    lead_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant.leads.id", ondelete="SET NULL"), nullable=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'accepted'"))
    conflict_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
