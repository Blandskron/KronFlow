from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TenantRuntime(Base):
    __tablename__ = "tenant_runtime"
    __table_args__ = (
        UniqueConstraint("auth_tenant_id", name="uniq_tenant_runtime_auth_tenant"),
        UniqueConstraint("schema_name", name="uniq_tenant_runtime_schema"),
        UniqueConstraint("tenant_code", name="uniq_tenant_runtime_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auth_tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tenant_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(63), nullable=False)
    tenant_code: Mapped[str] = mapped_column(String(64), nullable=False)
    ingest_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="starter")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    provisioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

