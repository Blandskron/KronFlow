from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TenantAgentProfile(Base):
    __tablename__ = "tenant_agent_profiles"
    __table_args__ = (UniqueConstraint("tenant_id", name="uniq_agent_profile_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, default="Flowkron Agent")
    tone: Mapped[str] = mapped_column(String(120), nullable=False, default="professional")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    context_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BusinessContextDocument(Base):
    __tablename__ = "business_context_documents"
    __table_args__ = (
        Index("idx_documents_tenant_status", "tenant_id", "status"),
        UniqueConstraint("tenant_id", "filename", "version", name="uniq_document_tenant_filename_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False, default="text/plain")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    chunks = relationship("DocumentChunk", cascade="all, delete-orphan")


class BusinessContextTemplate(Base):
    __tablename__ = "business_context_templates"
    __table_args__ = (UniqueConstraint("code", "format", name="uniq_template_code_format"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    format: Mapped[str] = mapped_column(String(24), nullable=False, default="form")
    fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BusinessContextForm(Base):
    __tablename__ = "business_context_forms"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uniq_form_tenant_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    fields = relationship("BusinessContextField", cascade="all, delete-orphan")


class BusinessContextField(Base):
    __tablename__ = "business_context_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_id: Mapped[int] = mapped_column(ForeignKey("business_context_forms.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    field_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class BusinessContextFormSubmission(Base):
    __tablename__ = "business_context_form_submissions"
    __table_args__ = (Index("idx_submissions_tenant_form", "tenant_id", "form_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    form_id: Mapped[int] = mapped_column(ForeignKey("business_context_forms.id", ondelete="CASCADE"), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (Index("idx_chunks_tenant_document", "tenant_id", "document_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("business_context_documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_ref: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="mock")
    vector: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    score_hint: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
