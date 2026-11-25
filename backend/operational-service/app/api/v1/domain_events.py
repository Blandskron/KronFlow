from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_resolver import TenantContext, resolve_audit_reader, resolve_crm_editor
from app.schemas.capture import (
    DomainEventAckIn,
    DomainEventPollOut,
    DomainEventReplayOut,
    DomainEventSubscriptionOut,
    DomainEventSubscriptionUpsertIn,
)
from app.services.domain_event_service import (
    ack_subscription_checkpoint,
    poll_subscription_events,
    replay_domain_events,
    upsert_subscription,
)


router = APIRouter(prefix="/api/v1/domain-events", tags=["Domain Events"])


@router.get("/replay", response_model=DomainEventReplayOut)
def replay_endpoint(
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    event_type: str | None = Query(default=None, max_length=80),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
):
    return replay_domain_events(
        db,
        tenant,
        after_id=after_id,
        limit=limit,
        event_types=[event_type] if event_type else None,
    )


@router.post("/subscriptions", response_model=DomainEventSubscriptionOut)
def upsert_subscription_endpoint(
    payload: DomainEventSubscriptionUpsertIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return upsert_subscription(
        db,
        tenant,
        subscriber_name=payload.subscriber_name,
        event_types=payload.event_types,
        is_active=payload.is_active,
    )


@router.get("/subscriptions/{subscriber_name}/poll", response_model=DomainEventPollOut)
def poll_subscription_endpoint(
    subscriber_name: str,
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
):
    return poll_subscription_events(db, tenant, subscriber_name=subscriber_name, limit=limit)


@router.post("/subscriptions/{subscriber_name}/ack", response_model=DomainEventSubscriptionOut)
def ack_subscription_endpoint(
    subscriber_name: str,
    payload: DomainEventAckIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return ack_subscription_checkpoint(
        db,
        tenant,
        subscriber_name=subscriber_name,
        through_event_id=payload.through_event_id,
    )
