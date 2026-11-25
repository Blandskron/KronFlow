from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BillingReference(Base):
    __tablename__ = "billing_reference"
    __table_args__ = (UniqueConstraint("auth_tenant_id", name="uniq_billing_reference_auth_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auth_tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    external_id: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="starter")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
