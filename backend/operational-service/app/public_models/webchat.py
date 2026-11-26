"""Public embeddable webchat widget registry mapped to tenant runtimes."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PublicWebchatWidget(Base):
    __tablename__ = "webchat_widgets"
    __table_args__ = {"schema": "public"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    auth_tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    widget_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allowed_origins: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    welcome_message: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
        default="¡Hola! ¿En qué podemos ayudarte hoy?",
    )
    session_ttl_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
