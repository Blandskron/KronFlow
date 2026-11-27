"""Public tenant-scoped security & privacy incident register with 3h CSIRT / 72h GDPR SLA tracking (PRV-024)."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SecurityIncident(Base):
    __tablename__ = "security_incidents"
    __table_args__ = (
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name="ck_security_incident_severity"),
        CheckConstraint("status IN ('open', 'contained', 'notified', 'closed')", name="ck_security_incident_status"),
        Index("idx_security_incidents_tenant_status", "auth_tenant_id", "status", "detected_at"),
        {"schema": "public"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    auth_tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'open'"))
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    affected_records_estimate: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    csirt_early_warning_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    authority_notice_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    containment_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
