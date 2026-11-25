"""Persistent commercial pipeline, opportunities, and activity history (FK-29)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PipelineStage(Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_pipeline_stage_slug"),
        CheckConstraint("position >= 0", name="ck_pipeline_stage_position"),
        CheckConstraint("stage_kind IN ('open', 'won', 'lost')", name="ck_pipeline_stage_kind"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'open'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint("outcome IN ('open', 'won', 'lost')", name="ck_opportunity_outcome"),
        CheckConstraint("version >= 1", name="ck_opportunity_version"),
        CheckConstraint("amount IS NULL OR amount >= 0", name="ck_opportunity_amount_non_negative"),
        Index("idx_opportunities_stage_owner", "stage_id", "owner_user_id", "id"),
        Index("idx_opportunities_contact", "contact_id", "id"),
        Index("idx_opportunities_outcome", "outcome", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.clientes.id", ondelete="RESTRICT"), nullable=False,
    )
    lead_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant.leads.id", ondelete="SET NULL"), nullable=True,
    )
    conversation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant.conversaciones.id", ondelete="SET NULL"), nullable=True,
    )
    stage_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.pipeline_stages.id", ondelete="RESTRICT"), nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'USD'"))
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'open'"))
    close_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class OpportunityActivity(Base):
    __tablename__ = "opportunity_activities"
    __table_args__ = (
        CheckConstraint(
            "activity_type IN ('created', 'stage_changed', 'owner_changed', 'closed_won', 'closed_lost', 'note', 'updated')",
            name="ck_opportunity_activity_type",
        ),
        Index("idx_opportunity_activities_opp", "opportunity_id", "id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.opportunities.id", ondelete="CASCADE"), nullable=False,
    )
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_stage_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    to_stage_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
