from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts import correlation_uuid
from app.core.tenant_resolver import TenantContext
from app.public_models.system_event import SystemEvent
from app.schemas.audit_event import AuditDomainEvent, AuditEventPage
from app.services.audit_event_catalog import EVENTS, TRANSITIONS


def project_event(event: SystemEvent) -> AuditDomainEvent:
    spec = EVENTS[event.event_type]
    payload = event.payload if isinstance(event.payload, dict) else {}
    data: dict[str, str | int] = {}
    resource_id = payload.get(spec.reference)
    if type(resource_id) is int and 1 <= resource_id <= 9223372036854775807:
        data[spec.reference] = resource_id
    if spec.transition is not None:
        for field in (spec.transition, f"previous_{spec.transition}"):
            value = payload.get(field)
            if isinstance(value, str) and value in TRANSITIONS[spec.transition]:
                data[field] = value
    event_id = f"operational:{event.id}"
    return AuditDomainEvent(
        event_id=event_id, event_type=spec.event_type, occurred_at=event.created_at,
        tenant_id=str(event.auth_tenant_id), correlation_id=correlation_uuid(payload.get("_correlation_id")) or event_id,
        data=data,
    )


def list_audit_events(
    db: Session, tenant: TenantContext, limit: int, before_id: int | None,
    event_type: str | None, correlation_id: UUID | None,
) -> AuditEventPage:
    types = [name for name, spec in EVENTS.items() if event_type is None or spec.event_type == event_type]
    if not types:
        raise HTTPException(status_code=422, detail="Unsupported audit event type")
    statement = select(SystemEvent).where(
        SystemEvent.auth_tenant_id == tenant.auth_tenant_id,
        SystemEvent.schema_name == tenant.schema_name,
        SystemEvent.event_type.in_(types),
    )
    if correlation_id is not None:
        statement = statement.where(SystemEvent.payload["_correlation_id"].astext == str(correlation_id))
    if before_id is not None:
        statement = statement.where(SystemEvent.id < before_id)
    rows = db.scalars(statement.order_by(SystemEvent.id.desc()).limit(limit + 1)).all()
    return AuditEventPage(items=[project_event(row) for row in rows[:limit]],
                          next_before_id=rows[limit - 1].id if len(rows) > limit else None)
