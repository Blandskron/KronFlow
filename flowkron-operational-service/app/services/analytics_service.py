from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.services.conversation_service import inbox_counts
from app.services.tenant_data import scalar_for_tenant
from app.tenant_models.operations import Lead, Message


def _count(db: Session, tenant: TenantContext, statement) -> int:
    return int(scalar_for_tenant(db, tenant.schema_name, statement) or 0)


def analytics_summary(db: Session, tenant: TenantContext) -> dict:
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)
    open_conversations, requires_human = inbox_counts(db, tenant)
    return {
        "total_leads": _count(db, tenant, select(func.count()).select_from(Lead)),
        "cold_leads": _count(db, tenant, select(func.count()).select_from(Lead).where(Lead.clasificacion == "frio")),
        "warm_leads": _count(db, tenant, select(func.count()).select_from(Lead).where(Lead.clasificacion == "tibio")),
        "hot_leads": _count(db, tenant, select(func.count()).select_from(Lead).where(Lead.clasificacion == "caliente")),
        "open_conversations": open_conversations,
        "requires_human": requires_human,
        "messages_today": _count(
            db,
            tenant,
            select(func.count()).select_from(Message).where(Message.creado_en >= today, Message.creado_en < now),
        ),
        "messages_last_7_days": _count(
            db,
            tenant,
            select(func.count()).select_from(Message).where(Message.creado_en >= seven_days_ago, Message.creado_en < now),
        ),
    }
