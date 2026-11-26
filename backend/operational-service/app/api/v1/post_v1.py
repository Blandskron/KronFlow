from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.post_v1 import (
    AppointmentConfirmIn,
    AppointmentOut,
    AppointmentSimulateIn,
    AppointmentSimulateOut,
    PrivateAttachmentCreateIn,
    PrivateAttachmentOut,
    WebhookDeliveryAttemptIn,
    WebhookDeliveryEnqueueIn,
    WebhookDeliveryOut,
    WebhookSubscriptionCreateIn,
    WebhookSubscriptionOut,
)
from app.services.post_v1_service import (
    MAX_ATTACHMENT_BYTES,
    cancel_appointment,
    confirm_appointment,
    create_webhook_subscription,
    enqueue_webhook_delivery,
    get_private_attachment,
    read_private_attachment_bytes,
    record_webhook_attempt,
    register_private_attachment,
    simulate_appointment_slot,
    upload_private_attachment_bytes,
)


router = APIRouter(prefix="/api/v1", tags=["Webhooks, Attachments & Scheduling"])


@router.post("/webhooks/subscriptions", response_model=WebhookSubscriptionOut, status_code=status.HTTP_201_CREATED)
def webhooks_create(
    payload: WebhookSubscriptionCreateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return create_webhook_subscription(
        db,
        tenant,
        name=payload.name,
        target_url=payload.target_url,
        event_types=payload.event_types,
        max_attempts=payload.max_attempts,
        actor_user_id=principal.user_id,
    )


@router.post("/webhooks/subscriptions/{subscription_id}/deliveries", response_model=WebhookDeliveryOut, status_code=status.HTTP_202_ACCEPTED)
def webhooks_enqueue(
    subscription_id: int,
    payload: WebhookDeliveryEnqueueIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return enqueue_webhook_delivery(
        db, tenant, subscription_id, event_id=payload.event_id, event_type=payload.event_type, payload=payload.payload,
    )


@router.post("/webhooks/deliveries/{delivery_id}/attempt", response_model=WebhookDeliveryOut)
def webhooks_attempt(
    delivery_id: int,
    payload: WebhookDeliveryAttemptIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return record_webhook_attempt(db, tenant, delivery_id, http_status=payload.http_status, error=payload.error)


@router.post("/attachments", response_model=PrivateAttachmentOut, status_code=status.HTTP_201_CREATED)
def attachments_register(
    payload: PrivateAttachmentCreateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return register_private_attachment(
        db,
        tenant,
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        sha256_hex=payload.sha256_hex,
        uploaded_by=principal.user_id,
        retention_days=payload.retention_days,
    )


@router.post("/attachments/upload", response_model=PrivateAttachmentOut, status_code=status.HTTP_201_CREATED)
async def attachments_upload(
    resource_type: Literal["conversation", "contact", "opportunity"] = Form(...),
    resource_id: int = Form(..., ge=1),
    retention_days: int = Form(default=90, ge=1, le=3650),
    file: UploadFile = File(...),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=422, detail=f"Attachment exceeds max size of {MAX_ATTACHMENT_BYTES} bytes")
    return upload_private_attachment_bytes(
        db,
        tenant,
        resource_type=resource_type,
        resource_id=resource_id,
        filename=file.filename or "attachment.bin",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        uploaded_by=principal.user_id,
        retention_days=retention_days,
    )


@router.get("/attachments/{attachment_id}/download")
def attachments_download(
    attachment_id: int,
    resource_type: Literal["conversation", "contact", "opportunity"] = Query(...),
    resource_id: int = Query(..., ge=1),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    meta, data = read_private_attachment_bytes(
        db,
        tenant,
        attachment_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    safe_filename = str(meta["filename"]).replace('"', "")
    return Response(
        content=data,
        media_type=meta["content_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/attachments/{attachment_id}", response_model=PrivateAttachmentOut)
def attachments_get(
    attachment_id: int,
    resource_type: Literal["conversation", "contact", "opportunity"] = Query(...),
    resource_id: int = Query(..., ge=1),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return get_private_attachment(db, tenant, attachment_id, resource_type=resource_type, resource_id=resource_id)


@router.post("/scheduling/simulate", response_model=AppointmentSimulateOut)
def scheduling_simulate(
    payload: AppointmentSimulateIn,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return simulate_appointment_slot(
        db, tenant, resource_key=payload.resource_key, starts_at=payload.starts_at, ends_at=payload.ends_at,
    )


@router.post("/scheduling/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def scheduling_confirm(
    payload: AppointmentConfirmIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return confirm_appointment(
        db,
        tenant,
        resource_key=payload.resource_key,
        client_id=payload.client_id,
        conversation_id=payload.conversation_id,
        title=payload.title,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        idempotency_key=payload.idempotency_key,
        actor_user_id=principal.user_id,
    )


@router.post("/scheduling/appointments/{appointment_id}/cancel", response_model=AppointmentOut)
def scheduling_cancel(
    appointment_id: int,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return cancel_appointment(db, tenant, appointment_id)
