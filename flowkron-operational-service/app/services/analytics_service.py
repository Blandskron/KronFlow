from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.services.conversation_service import inbox_counts_statement
from app.services.tenant_data import execute_for_tenant
from app.tenant_models.operations import Lead, Message


def analytics_summary(db: Session, tenant: TenantContext) -> dict:
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)
    leads = select(
        func.count().label("total_leads"),
        func.count().filter(Lead.clasificacion == "frio").label("cold_leads"),
        func.count().filter(Lead.clasificacion == "tibio").label("warm_leads"),
        func.count().filter(Lead.clasificacion == "caliente").label("hot_leads"),
    ).select_from(Lead).subquery()
    inbox = inbox_counts_statement().subquery()
    messages = select(
        func.count().filter(Message.creado_en >= today).label("messages_today"),
        func.count().label("messages_last_7_days"),
    ).where(Message.creado_en >= seven_days_ago, Message.creado_en < now).subquery()
    # Each subquery yields one row. A single statement gives all counts the same PostgreSQL snapshot.
    statement = select(leads, inbox, messages).select_from(leads.join(inbox, true()).join(messages, true()))
    return dict(execute_for_tenant(db, tenant.schema_name, statement).mappings().one())
