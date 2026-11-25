"""Versioned domain event persistence, forward replay, and tenant subscriptions (FK-10)."""

from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.contracts import audit_correlation
from app.core.tenant_resolver import TenantContext
from app.services.tenant_data import bind_tenant_session
from app.tenant_models.domain_events import DomainEvent, DomainEventSubscription


MAX_REPLAY_BATCH = 200


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Domain event timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def domain_events_ready(db: Session, tenant: TenantContext) -> bool:
    inspector = inspect(db.connection())
    return (
        inspector.has_table(DomainEvent.__tablename__, schema=tenant.schema_name)
        and inspector.has_table(DomainEventSubscription.__tablename__, schema=tenant.schema_name)
    )


def _require_ready(db: Session, tenant: TenantContext) -> None:
    if not domain_events_ready(db, tenant):
        raise HTTPException(status_code=503, detail="Domain event store schema is unavailable")


def _event_to_dict(event: DomainEvent, tenant: TenantContext) -> dict:
    return {
        "id": event.id,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "tenant_id": str(tenant.auth_tenant_id),
        "aggregate_type": event.aggregate_type,
        "aggregate_id": event.aggregate_id,
        "correlation_id": event.correlation_id or event.event_id,
        "payload": event.payload,
        "occurred_at": event.occurred_at,
    }


def _subscription_to_dict(sub: DomainEventSubscription) -> dict:
    return {
        "id": sub.id,
        "subscriber_name": sub.subscriber_name,
        "event_types": list(sub.event_types or []),
        "last_event_id": sub.last_event_id,
        "is_active": sub.is_active,
        "updated_at": sub.updated_at,
    }


def publish_domain_event_in_tx(
    db: Session,
    tenant: TenantContext,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str | int,
    payload: dict,
    schema_version: int = 1,
    correlation_id: str | None = None,
    occurred_at: datetime | None = None,
) -> DomainEvent | None:
    """Persist a versioned domain event inside the caller's already-bound tenant transaction."""
    if not domain_events_ready(db, tenant):
        return None
    current = _now(occurred_at)
    event = DomainEvent(
        event_id=f"evt_{uuid4().hex}",
        event_type=event_type.strip()[:80],
        schema_version=max(1, int(schema_version)),
        aggregate_type=aggregate_type.strip()[:32],
        aggregate_id=str(aggregate_id)[:64],
        correlation_id=(correlation_id or audit_correlation.get()),
        payload=dict(payload),
        occurred_at=current,
    )
    db.add(event)
    db.flush()
    return event


def replay_domain_events(
    db: Session,
    tenant: TenantContext,
    *,
    after_id: int = 0,
    limit: int = 50,
    event_types: Sequence[str] | None = None,
) -> dict:
    """Deterministic forward replay from cursor `after_id` (ORDER BY id ASC)."""
    limit = max(1, min(limit, MAX_REPLAY_BATCH))
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    stmt = select(DomainEvent).where(DomainEvent.id > max(0, after_id))
    if event_types:
        stmt = stmt.where(DomainEvent.event_type.in_(tuple(event_types)))
    rows = list(db.scalars(stmt.order_by(DomainEvent.id.asc()).limit(limit + 1)).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    next_after_id = page[-1].id if page else max(0, after_id)
    return {
        "items": [_event_to_dict(row, tenant) for row in page],
        "next_after_id": next_after_id,
        "has_more": has_more,
    }


def upsert_subscription(
    db: Session,
    tenant: TenantContext,
    *,
    subscriber_name: str,
    event_types: Sequence[str] | None = None,
    is_active: bool = True,
    now: datetime | None = None,
) -> dict:
    clean_name = subscriber_name.strip()
    if not clean_name or len(clean_name) > 64:
        raise HTTPException(status_code=422, detail="subscriber_name must be 1..64 characters")
    cleaned_types = sorted({t.strip() for t in (event_types or []) if t and t.strip()})
    current = _now(now)

    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    db.execute(
        insert(DomainEventSubscription)
        .values(
            subscriber_name=clean_name,
            event_types=cleaned_types,
            last_event_id=0,
            is_active=bool(is_active),
            updated_at=current,
        )
        .on_conflict_do_update(
            index_elements=["subscriber_name"],
            set_={
                "event_types": cleaned_types,
                "is_active": bool(is_active),
                "updated_at": current,
            },
        )
    )
    db.commit()
    sub = db.scalar(select(DomainEventSubscription).where(DomainEventSubscription.subscriber_name == clean_name))
    return _subscription_to_dict(sub)


def poll_subscription_events(
    db: Session,
    tenant: TenantContext,
    *,
    subscriber_name: str,
    limit: int = 50,
) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    sub = db.scalar(select(DomainEventSubscription).where(DomainEventSubscription.subscriber_name == subscriber_name.strip()))
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if not sub.is_active:
        raise HTTPException(status_code=409, detail="Subscription is inactive")

    result = replay_domain_events(
        db,
        tenant,
        after_id=sub.last_event_id,
        limit=limit,
        event_types=sub.event_types if sub.event_types else None,
    )
    result["subscriber_name"] = sub.subscriber_name
    result["checkpoint_id"] = sub.last_event_id
    return result


def ack_subscription_checkpoint(
    db: Session,
    tenant: TenantContext,
    *,
    subscriber_name: str,
    through_event_id: int,
    now: datetime | None = None,
) -> dict:
    if through_event_id < 0:
        raise HTTPException(status_code=422, detail="through_event_id must be >= 0")
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    sub = db.scalar(
        select(DomainEventSubscription)
        .where(DomainEventSubscription.subscriber_name == subscriber_name.strip())
        .with_for_update()
    )
    if sub is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Subscription not found")
    # Monotonic checkpoint advance prevents regressing past already-acknowledged events.
    if through_event_id > sub.last_event_id:
        sub.last_event_id = through_event_id
        sub.updated_at = current
    db.commit()
    db.refresh(sub)
    return _subscription_to_dict(sub)
