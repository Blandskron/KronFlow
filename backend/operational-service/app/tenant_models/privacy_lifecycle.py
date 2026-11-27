"""Configurable per-tenant data retention policy with legal-hold support (PRV-017)."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TenantRetentionPolicy(Base):
    __tablename__ = "tenant_retention_policies"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_tenant_retention_policy_singleton"),
        CheckConstraint("messages_retention_days BETWEEN 1 AND 3650", name="ck_ret_messages_days"),
        CheckConstraint("memory_retention_days BETWEEN 1 AND 3650", name="ck_ret_memory_days"),
        CheckConstraint("attachments_retention_days BETWEEN 1 AND 3650", name="ck_ret_attachments_days"),
        CheckConstraint("voice_retention_days BETWEEN 1 AND 3650", name="ck_ret_voice_days"),
        CheckConstraint("traces_retention_days BETWEEN 1 AND 3650", name="ck_ret_traces_days"),
        CheckConstraint("webchat_retention_days BETWEEN 1 AND 3650", name="ck_ret_webchat_days"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default=text("1"))
    messages_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("180"))
    memory_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("90"))
    attachments_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("90"))
    voice_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("90"))
    traces_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("90"))
    webchat_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("90"))
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    legal_hold_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    last_swept_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class TenantSubprocessorApproval(Base):
    """Per-tenant auditable subprocessor approval registry for international transfers (PRV-020)."""

    __tablename__ = "tenant_subprocessor_approvals"
    __table_args__ = {"schema": "tenant"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_key: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    jurisdiction: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'US'"))
    subprocessor_list_version: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'2026-11-v1'"))
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
