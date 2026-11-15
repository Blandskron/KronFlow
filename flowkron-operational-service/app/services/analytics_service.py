from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.services.tenant_data import scalar_for_tenant
from app.tenant_models.operations import Lead, Message


def _count(db: Session, tenant: TenantContext, statement) -> int:
    return int(scalar_for_tenant(db, tenant.schema_name, statement) or 0)


def analytics_summary(db: Session, tenant: TenantContext) -> dict:
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = datetime.now(UTC) - timedelta(days=7)
    return {
        "total_leads": _count(db, tenant, select(func.count()).select_from(Lead)),
        "cold_leads": _count(db, tenant, select(func.count()).select_from(Lead).where(Lead.clasificacion == "frio")),
        "warm_leads": _count(db, tenant, select(func.count()).select_from(Lead).where(Lead.clasificacion == "tibio")),
        "hot_leads": _count(db, tenant, select(func.count()).select_from(Lead).where(Lead.clasificacion == "caliente")),
        "open_conversations": _count(
            db,
            tenant,
            select(func.count()).select_from(Lead).where(Lead.estado.in_(["nuevo", "contactado", "en_proceso"])),
        ),
        "requires_human": _count(
            db,
            tenant,
            select(func.count()).select_from(Lead).where(Lead.estado_seguimiento == "requiere_humano"),
        ),
        "messages_today": _count(
            db,
            tenant,
            select(func.count()).select_from(Message).where(Message.creado_en >= today),
        ),
        "messages_last_7_days": _count(
            db,
            tenant,
            select(func.count()).select_from(Message).where(Message.creado_en >= seven_days_ago),
        ),
    }
