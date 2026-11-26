"""Public opaque self-service unsubscribe tokens."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PublicUnsubscribeToken(Base):
    __tablename__ = "public_unsubscribe_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_public_unsub_token_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    schema_name: Mapped[str] = mapped_column(String(63), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
