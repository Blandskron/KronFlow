"""Multi-agent immutable revisions, delegated rules, execution traces, and setup-chat sessions (tenant_schema_v17)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentRevision(Base):
    __tablename__ = "agent_revisions"
    __table_args__ = (
        UniqueConstraint("agent_id", "revision_number", name="uq_agent_revision_num"),
        CheckConstraint("revision_number >= 1", name="ck_agent_revision_positive"),
        CheckConstraint("status IN ('active', 'superseded', 'rolled_back')", name="ck_agent_revision_status"),
        Index("idx_agent_revisions_agent_status", "agent_id", "status", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenant.tenant_agent_profiles.id", ondelete="CASCADE"), nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'active'"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(160), nullable=False)
    tone: Mapped[str] = mapped_column(String(120), nullable=False, server_default=text("'professional'"))
    language: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'es'"))
    instructions: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    allowed_tools: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    allowed_document_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    limits_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    prompt_config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    publish_note: Mapped[str | None] = mapped_column(String(240), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AgentRule(Base):
    __tablename__ = "agent_rules"
    __table_args__ = (
        Index("idx_agent_rules_tenant_priority", "tenant_id", "priority", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tenant.tenant_agent_profiles.id", ondelete="SET NULL"), nullable=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(48), nullable=False, server_default=text("'general'"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AgentExecutionTrace(Base):
    __tablename__ = "agent_execution_traces"
    __table_args__ = (
        Index("idx_agent_traces_conv_created", "tenant_id", "conversation_id", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_revision_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    output_message: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    requires_human: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_simulation: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    actions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SetupChatSession(Base):
    __tablename__ = "setup_chat_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'generated', 'published')", name="ck_setup_chat_status"),
        Index("idx_setup_chat_tenant", "tenant_id", "created_at"),
        {"schema": "tenant"},
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    objective: Mapped[str] = mapped_column(String(120), nullable=False, server_default=text("'build_business_context'"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'draft'"))
    messages: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    generated_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
