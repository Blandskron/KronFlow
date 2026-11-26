from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import Date, cast, func, inspect, literal, select, true, union_all
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.analytics import (
    AIUsageKpis,
    ActivityCounts,
    ActivityDay,
    AnalyticsActivity,
    AnalyticsKpisOut,
    AnalyticsSummary,
    CampaignKpis,
    EventCoverageKpis,
    GovernanceKpis,
    PipelineKpis,
    WorkflowKpis,
)
from app.services.ai_extensions_service import summarize_ai_usage
from app.services.conversation_service import inbox_counts_statement
from app.services.tenant_data import bind_tenant_session, execute_for_tenant
from app.tenant_models.ai_extensions import AIUsageRecord
from app.tenant_models.ai_proposal import AIActionProposal
from app.tenant_models.campaigns import Campaign, CampaignRecipient
from app.tenant_models.domain_events import DomainEvent
from app.tenant_models.operations import Cliente, Lead, Message, SolicitudDerecho
from app.tenant_models.opportunity import Opportunity
from app.tenant_models.workflows import WorkflowDefinition, WorkflowRun


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


def analytics_kpis(db: Session, tenant: TenantContext) -> AnalyticsKpisOut:
    """Consolidated event-calibrated KPIs for pipeline, campaigns, events, and governance (FK-09)."""
    as_of = datetime.now(UTC)
    bind_tenant_session(db, tenant.schema_name)
    inspector = inspect(db.connection())
    existing_tables = set(inspector.get_table_names(schema=tenant.schema_name))

    pipeline = PipelineKpis()
    if Opportunity.__tablename__ in existing_tables:
        opp_counts = dict(
            db.execute(select(Opportunity.outcome, func.count()).group_by(Opportunity.outcome)).all()
        )
        open_c = int(opp_counts.get("open", 0))
        won_c = int(opp_counts.get("won", 0))
        lost_c = int(opp_counts.get("lost", 0))
        won_amounts = {
            currency: str(total)
            for currency, total in db.execute(
                select(Opportunity.currency, func.coalesce(func.sum(Opportunity.amount), 0))
                .where(Opportunity.outcome == "won")
                .group_by(Opportunity.currency)
            ).all()
        }
        closed_total = won_c + lost_c
        pipeline = PipelineKpis(
            open_opportunities=open_c,
            won_opportunities=won_c,
            lost_opportunities=lost_c,
            won_amount_by_currency=won_amounts,
            win_rate=round(won_c / closed_total, 4) if closed_total > 0 else None,
        )

    campaigns = CampaignKpis()
    if Campaign.__tablename__ in existing_tables and CampaignRecipient.__tablename__ in existing_tables:
        total_camps = int(db.scalar(select(func.count()).select_from(Campaign)) or 0)
        rec_counts = {
            status_name: int(cnt)
            for status_name, cnt in db.execute(
                select(CampaignRecipient.status, func.count()).group_by(CampaignRecipient.status)
            ).all()
        }
        accepted_base = (
            rec_counts.get("accepted", 0)
            + rec_counts.get("delivered", 0)
            + rec_counts.get("bounced", 0)
            + rec_counts.get("complained", 0)
            + rec_counts.get("unsubscribed", 0)
        )
        delivered_c = rec_counts.get("delivered", 0)
        campaigns = CampaignKpis(
            total_campaigns=total_camps,
            recipients_queued=rec_counts.get("queued", 0),
            recipients_accepted=accepted_base,
            recipients_delivered=delivered_c,
            recipients_suppressed=rec_counts.get("suppressed", 0),
            recipients_bounced=rec_counts.get("bounced", 0),
            recipients_unsubscribed=rec_counts.get("unsubscribed", 0),
            delivery_rate=round(delivered_c / accepted_base, 4) if accepted_base > 0 else None,
        )

    events = EventCoverageKpis()
    if DomainEvent.__tablename__ in existing_tables:
        by_type = {
            ev_type: int(cnt)
            for ev_type, cnt in db.execute(
                select(DomainEvent.event_type, func.count()).group_by(DomainEvent.event_type)
            ).all()
        }
        last_id = int(db.scalar(select(func.coalesce(func.max(DomainEvent.id), 0))) or 0)
        events = EventCoverageKpis(
            total_domain_events=sum(by_type.values()),
            event_counts_by_type=by_type,
            last_event_id=last_id,
        )

    open_cases = int(
        db.scalar(select(func.count()).select_from(SolicitudDerecho).where(SolicitudDerecho.estado != "completada")) or 0
    )
    pending_props = 0
    executed_props = 0
    if AIActionProposal.__tablename__ in existing_tables:
        prop_counts = dict(
            db.execute(select(AIActionProposal.status, func.count()).group_by(AIActionProposal.status)).all()
        )
        pending_props = int(prop_counts.get("pending", 0))
        executed_props = int(prop_counts.get("executed", 0))

    governance = GovernanceKpis(
        open_privacy_cases=open_cases,
        pending_ai_proposals=pending_props,
        executed_ai_proposals=executed_props,
    )

    ai_usage = AIUsageKpis()
    if AIUsageRecord.__tablename__ in existing_tables:
        usage_summary = summarize_ai_usage(db, tenant, days=30, include_simulations=False, now=as_of)
        ai_usage = AIUsageKpis(**usage_summary)

    workflows = WorkflowKpis()
    if WorkflowDefinition.__tablename__ in existing_tables and WorkflowRun.__tablename__ in existing_tables:
        active_wf = int(
            db.scalar(select(func.count()).select_from(WorkflowDefinition).where(WorkflowDefinition.status == "active")) or 0
        )
        run_counts = dict(db.execute(select(WorkflowRun.status, func.count()).group_by(WorkflowRun.status)).all())
        workflows = WorkflowKpis(
            active_workflows=active_wf,
            runs_running=int(run_counts.get("running", 0)),
            runs_waiting=int(run_counts.get("waiting", 0)),
            runs_completed=int(run_counts.get("completed", 0)),
            runs_failed=int(run_counts.get("failed", 0)),
            runs_cancelled=int(run_counts.get("cancelled", 0)),
        )

    return AnalyticsKpisOut(
        as_of=as_of,
        pipeline=pipeline,
        campaigns=campaigns,
        events=events,
        governance=governance,
        ai_usage=ai_usage,
        workflows=workflows,
    )

