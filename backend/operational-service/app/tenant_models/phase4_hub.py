"""Tenant-scoped governed tool registry, invocations, and webchat visitor sessions."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ToolDefinition(Base):
    __tablename__ = "tool_definitions"
    __table_args__ = {"schema": "tenant"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tool_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    effect_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="read_only")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    required_permission: Mapped[str] = mapped_column(String(64), nullable=False, default="crm.manage")
    connector_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_calls_per_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ToolInvocation(Base):
    __tablename__ = "tool_invocations"
    __table_args__ = (
        UniqueConstraint("tool_key", "idempotency_key", name="uq_tool_invocation_idem"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tool_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenant.tool_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    arguments_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    effect_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    proposal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outbox_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invoked_by: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WebchatSession(Base):
    __tablename__ = "webchat_sessions"
    __table_args__ = {"schema": "tenant"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    widget_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    visitor_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    visitor_email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    origin: Mapped[str] = mapped_column(String(255), nullable=False)
    client_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenant.clientes.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenant.conversaciones.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
