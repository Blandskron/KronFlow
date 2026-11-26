"""Voice/telephony session API endpoints and signed Twilio webhook."""

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.voice import (
    VoiceCallCompleteIn,
    VoiceCallCreateIn,
    VoiceCallSegmentIn,
    VoiceCallTransferIn,
)
from app.services.voice_service import (
    append_voice_segment,
    complete_voice_call,
    get_voice_call,
    ingest_twilio_voice_webhook,
    list_voice_calls,
    start_voice_call,
    transfer_voice_call,
)


router = APIRouter(prefix="/api/v1", tags=["Voice"])


@router.get("/voice/calls")
def list_voice_calls_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    _principal: CurrentPrincipal = Depends(require_permission("users.read")),
    db: Session = Depends(get_db),
):
    return list_voice_calls(db, tenant, limit=limit)


@router.get("/voice/calls/{call_id}")
def get_voice_call_endpoint(
    call_id: int,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    _principal: CurrentPrincipal = Depends(require_permission("users.read")),
    db: Session = Depends(get_db),
):
    return get_voice_call(db, tenant, call_id)


@router.post("/voice/calls")
def start_voice_call_endpoint(
    payload: VoiceCallCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    _principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return start_voice_call(db, tenant, payload)


@router.post("/voice/calls/{call_id}/segments")
def append_voice_segment_endpoint(
    call_id: int,
    payload: VoiceCallSegmentIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    _principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return append_voice_segment(db, tenant, call_id, payload)


@router.post("/voice/calls/{call_id}/transfer")
def transfer_voice_call_endpoint(
    call_id: int,
    payload: VoiceCallTransferIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return transfer_voice_call(db, tenant, call_id, payload, actor_user_id=principal.user_id)


@router.post("/voice/calls/{call_id}/complete")
def complete_voice_call_endpoint(
    call_id: int,
    payload: VoiceCallCompleteIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    _principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return complete_voice_call(db, tenant, call_id, payload)


@router.post("/public/webhooks/voice/twilio")
async def twilio_voice_webhook_endpoint(
    request: Request,
    x_twilio_signature_256: str | None = Header(default=None, alias="X-Twilio-Signature-256"),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    payload = await request.json()
    return ingest_twilio_voice_webhook(
        db,
        raw_body=raw_body,
        signature_header=x_twilio_signature_256,
        payload=payload if isinstance(payload, dict) else {},
    )
