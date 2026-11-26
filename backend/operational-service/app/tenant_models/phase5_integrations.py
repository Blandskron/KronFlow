"""External entity sync mappings, conflict reconciliation, and incremental connector cursors."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExternalEntityMapping(Base):
    __tablename__ = "external_entity_mappings"
    __table_args__ = (
        UniqueConstraint("connection_ref", "resource_type", "remote_id", name="uq_ext_mapping_conn_resource_remote"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    connection_ref: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    remote_id: Mapped[str] = mapped_column(String(160), nullable=False)
    local_type: Mapped[str] = mapped_column(String(32), nullable=False)
    local_id: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    local_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sync_state: Mapped[str] = mapped_column(String(24), nullable=False, default="synced")
    conflict_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ConnectorSyncCursor(Base):
    __tablename__ = "connector_sync_cursors"
    __table_args__ = (
        UniqueConstraint("connection_ref", "stream_name", name="uq_sync_cursor_conn_stream"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    connection_ref: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    stream_name: Mapped[str] = mapped_column(String(64), nullable=False)
    cursor_value: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ok")
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    synced_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
