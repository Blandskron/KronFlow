from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import Date, cast, func, literal, select, true, union_all
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.analytics import ActivityCounts, ActivityDay, AnalyticsActivity
from app.services.conversation_service import inbox_counts_statement
from app.services.tenant_data import execute_for_tenant
from app.tenant_models.operations import Cliente, Lead, Message


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


def analytics_activity(
    db: Session, tenant: TenantContext, start_date: date, end_date: date, time_zone: str,
) -> AnalyticsActivity:
    day_count = (end_date - start_date).days + 1
    if not 1 <= day_count <= 31 or start_date.year < 2 or end_date.year > 9998:
        raise HTTPException(status_code=422, detail="Choose an ordered date range of up to 31 days")

    # Validate against the same time-zone database used to aggregate (including its historical rules).
    zones = func.pg_timezone_names().table_valued("name")
    if not db.scalar(select(select(zones.c.name).where(zones.c.name == time_zone).exists())):
        raise HTTPException(status_code=422, detail="Unknown IANA time zone")
    as_of = datetime.now(UTC)
    local_today = db.scalar(select(cast(func.timezone(time_zone, as_of), Date)))
    if end_date > local_today:
        raise HTTPException(status_code=422, detail="The end date is in the future in the selected time zone")

    # A broad UTC bound covers all local offsets, including ambiguous midnights. The local date is authoritative.
    lower = datetime.combine(start_date, time.min, UTC) - timedelta(days=1)
    upper = min(datetime.combine(end_date, time.min, UTC) + timedelta(days=2), as_of)

    def grouped(timestamp, metric, *group_by):
        local_day = cast(func.timezone(time_zone, timestamp), Date)
        return select(local_day.label("day"), metric.label("metric"), func.count().label("total")).where(
            timestamp >= lower, timestamp < upper, local_day.between(start_date, end_date)
        ).group_by(local_day, *group_by)

    statement = union_all(
        grouped(Cliente.creado_en, literal("contacts_created")),
        grouped(Lead.creado_en, literal("leads_created")),
        grouped(Message.creado_en, func.concat(Message.direction, "_messages"), Message.direction),
    )
    by_day = {start_date + timedelta(days=offset): {} for offset in range(day_count)}
    for day, metric, total in execute_for_tenant(db, tenant.schema_name, statement):
        by_day[day][metric] = total
    totals = {metric: sum(counts.get(metric, 0) for counts in by_day.values()) for metric in ActivityCounts.model_fields}
    return AnalyticsActivity(
        start_date=start_date, end_date=end_date, time_zone=time_zone, as_of=as_of,
        partial_day=local_today if end_date == local_today else None, totals=ActivityCounts(**totals),
        days=[ActivityDay(day=day, **counts) for day, counts in by_day.items()],
    )
