"""Durable versioned domain events and tenant-scoped replay subscriptions (FK-10)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DomainEvent(Base):
    __tablename__ = "domain_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_domain_event_id"),
        CheckConstraint("schema_version >= 1", name="ck_domain_event_schema_version"),
        Index("idx_domain_events_type_id", "event_type", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    aggregate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class DomainEventSubscription(Base):
    __tablename__ = "domain_event_subscriptions"
    __table_args__ = (
        UniqueConstraint("subscriber_name", name="uq_domain_event_subscriber"),
        CheckConstraint("last_event_id >= 0", name="ck_domain_event_sub_checkpoint"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subscriber_name: Mapped[str] = mapped_column(String(64), nullable=False)
    event_types: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    last_event_id: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
