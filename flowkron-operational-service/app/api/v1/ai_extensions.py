from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.ai_extensions import (
    AIUsageCreateIn,
    AIUsageOut,
    AIUsageSummaryOut,
    ContactEnrichmentApplyIn,
    ContactEnrichmentCreateIn,
    ContactEnrichmentOut,
    ConversationMemoryCreateIn,
    ConversationMemoryOut,
    ExternalNotificationCreateIn,
    ExternalNotificationOut,
    ExternalNotificationReceiptIn,
)
from app.services.ai_extensions_service import (
    apply_contact_enrichment,
    enqueue_external_notification,
    list_conversation_memory,
    propose_contact_enrichment,
    record_ai_usage,
    record_conversation_memory,
    record_notification_receipt,
    summarize_ai_usage,
)


router = APIRouter(prefix="/api/v1", tags=["AI Extensions & Notifications"])


@router.get("/conversations/{conversation_id}/memory", response_model=list[ConversationMemoryOut])
def memory_list(
    conversation_id: int,
    limit: int = Query(default=20, ge=1, le=50),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return list_conversation_memory(db, tenant, conversation_id, limit=limit)


@router.post(
    "/conversations/{conversation_id}/memory",
    response_model=ConversationMemoryOut,
    status_code=status.HTTP_201_CREATED,
)
def memory_create(
    conversation_id: int,
    payload: ConversationMemoryCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return record_conversation_memory(
        db,
        tenant,
        conversation_id,
        memory_key=payload.memory_key,
        memory_value=payload.memory_value,
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        ttl_days=payload.ttl_days,
    )


@router.post(
    "/contacts/{contact_id}/enrichments",
    response_model=ContactEnrichmentOut,
    status_code=status.HTTP_201_CREATED,
)
def enrichment_propose(
    contact_id: int,
    payload: ContactEnrichmentCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return propose_contact_enrichment(
        db,
        tenant,
        contact_id,
        field_name=payload.field_name,
        proposed_value=payload.proposed_value,
        source=payload.source,
    )


@router.post("/contacts/enrichments/{candidate_id}/apply", response_model=ContactEnrichmentOut)
def enrichment_apply(
    candidate_id: int,
    payload: ContactEnrichmentApplyIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return apply_contact_enrichment(
        db,
        tenant,
        candidate_id,
        reviewer_user_id=principal.user_id,
        allow_overwrite=payload.allow_overwrite,
    )


@router.post("/notifications/external", response_model=ExternalNotificationOut, status_code=status.HTTP_202_ACCEPTED)
def notification_enqueue(
    payload: ExternalNotificationCreateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return enqueue_external_notification(
        db,
        tenant,
        dedup_key=payload.dedup_key,
        event_type=payload.event_type,
        channel=payload.channel,
        recipient=payload.recipient,
        payload=payload.payload,
        actor_user_id=principal.user_id,
    )


@router.post("/notifications/external/{delivery_id}/receipt", response_model=ExternalNotificationOut)
def notification_receipt(
    delivery_id: int,
    payload: ExternalNotificationReceiptIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return record_notification_receipt(
        db, tenant, delivery_id, status_value=payload.status, receipt_ref=payload.receipt_ref,
    )


@router.post("/analytics/ai-usage", response_model=AIUsageOut, status_code=status.HTTP_201_CREATED)
def ai_usage_create(
    payload: AIUsageCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return record_ai_usage(
        db,
        tenant,
        provider=payload.provider,
        model=payload.model,
        prompt_tokens=payload.prompt_tokens,
        completion_tokens=payload.completion_tokens,
        latency_ms=payload.latency_ms,
        estimated_cost_usd=payload.estimated_cost_usd,
        correlation_id=payload.correlation_id,
    )


@router.get("/analytics/ai-usage/summary", response_model=AIUsageSummaryOut)
def ai_usage_summary(
    days: int = Query(default=30, ge=1, le=365),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return summarize_ai_usage(db, tenant, days=days)
