from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WhatsAppConsentState(Base):
    __tablename__ = "whatsapp_consent_state"
    __table_args__ = {"schema": "tenant"}

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.clientes.id", ondelete="CASCADE"), primary_key=True,
    )
    decision_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    authorized_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
