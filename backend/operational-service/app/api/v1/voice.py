"""Voice/telephony session API endpoints, signed Twilio webhook, and realtime Media Streams WS."""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
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
from app.services.capture_service import authenticate_scoped_credential
from app.services.tenant_data import bind_tenant_session
from app.services.voice_service import (
    append_voice_segment,
    complete_voice_call,
    get_voice_call,
    ingest_twilio_voice_webhook,
    list_voice_calls,
    start_voice_call,
    transfer_voice_call,
)
from app.tenant_models.phase6_extensions import VoiceCallSegment, VoiceCallSession


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


@router.websocket("/voice/media-stream/{call_id}")
async def twilio_media_stream_websocket(
    websocket: WebSocket,
    call_id: int,
    db: Session = Depends(get_db),
):
    api_key = websocket.query_params.get("api_key") or websocket.headers.get("x-flowkron-key")
    if not api_key:
        await websocket.close(code=4401, reason="Missing scoped credential")
        return
    try:
        tenant, _cred = authenticate_scoped_credential(db, api_key, required_scope="mcp:invoke")
    except HTTPException as exc:
        await websocket.close(code=4401 if exc.status_code == 401 else 4403, reason=str(exc.detail))
        return

    bind_tenant_session(db, tenant.schema_name)
    call = db.get(VoiceCallSession, call_id)
    if call is None:
        await websocket.close(code=4404, reason="Voice call session not found")
        return

    max_seq = int(
        db.scalar(select(func.coalesce(func.max(VoiceCallSegment.sequence_no), 0)).where(VoiceCallSegment.call_id == call_id))
        or 0
    )
    next_seq = max_seq + 1
    stream_sid = f"stream_{call_id}"
    frames_received = 0
    bytes_received = 0

    await websocket.accept()
    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                frame = json.loads(raw_text)
            except json.JSONDecodeError:
                await websocket.send_json({"event": "error", "detail": "Invalid JSON frame"})
                continue

            event_type = str(frame.get("event") or "").strip().lower()
            if event_type == "start":
                start_obj = frame.get("start") if isinstance(frame.get("start"), dict) else {}
                stream_sid = str(frame.get("streamSid") or start_obj.get("streamSid") or stream_sid)
                await websocket.send_json({"event": "connected", "call_id": call_id, "streamSid": stream_sid})
            elif event_type == "media":
                media_obj = frame.get("media") if isinstance(frame.get("media"), dict) else {}
                payload_chunk = str(media_obj.get("payload") or "")
                frames_received += 1
                bytes_received += len(payload_chunk)
                transcript = str(frame.get("transcript") or media_obj.get("transcript") or "").strip()
                if transcript:
                    append_voice_segment(
                        db,
                        tenant,
                        call_id,
                        VoiceCallSegmentIn(sequence_no=next_seq, speaker="caller", transcript=transcript, is_barge_in=False),
                    )
                    next_seq += 1
            elif event_type == "barge_in":
                await websocket.send_json({"event": "clear", "streamSid": stream_sid})
                transcript = str(frame.get("transcript") or "[barge_in]").strip()
                append_voice_segment(
                    db,
                    tenant,
                    call_id,
                    VoiceCallSegmentIn(sequence_no=next_seq, speaker="caller", transcript=transcript, is_barge_in=True),
                )
                next_seq += 1
            elif event_type == "stop":
                secs = int(frame.get("billable_seconds") or 0)
                complete_voice_call(
                    db,
                    tenant,
                    call_id,
                    VoiceCallCompleteIn(status="completed", billable_seconds=max(0, secs), close_reason="media_stream_stopped"),
                )
                await websocket.send_json(
                    {
                        "event": "stopped",
                        "call_id": call_id,
                        "streamSid": stream_sid,
                        "frames_received": frames_received,
                        "bytes_received": bytes_received,
                    }
                )
                await websocket.close(code=1000)
                return
    except WebSocketDisconnect:
        return
