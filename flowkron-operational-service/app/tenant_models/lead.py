from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("phone", name="uniq_leads_phone"),
        Index("idx_leads_temperature", "temperature"),
        Index("idx_leads_lifecycle_status", "lifecycle_status"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(180), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(48), nullable=False)
    email: Mapped[str] = mapped_column(String(180), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="whatsapp")
    direction: Mapped[str] = mapped_column(String(24), nullable=False, default="inbound")
    temperature: Mapped[str] = mapped_column(String(24), nullable=False, default="cold")
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    assigned_to_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
