"""Public irreversible erasure tombstones for post-restore backup reconciliation (PRV-019)."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PrivacyErasureTombstone(Base):
    __tablename__ = "privacy_erasure_tombstones"
    __table_args__ = (
        Index("idx_erasure_tombstones_schema_hash", "schema_name", "subject_hash"),
        {"schema": "public"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    auth_tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    schema_name: Mapped[str] = mapped_column(String(63), nullable=False)
    identifier_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    case_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    erased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
