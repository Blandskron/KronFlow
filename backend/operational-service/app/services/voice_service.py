"""Voice/telephony session service, idempotent transcripts, barge-in, HITL handoff, and Twilio ingest."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
from typing import Any

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext, ensure_runtime_is_usable
from app.public_models.channel_route import PublicChannelWebhookRoute
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.voice import (
    VoiceCallCompleteIn,
    VoiceCallCreateIn,
    VoiceCallSegmentIn,
    VoiceCallTransferIn,
)
from app.services.conversation_control_service import mark_waiting_human_in_tx
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.lead_service import get_or_create_initial_lead
from app.services.tenant_data import bind_tenant_session
from app.services.workflow_cancellation import cancel_waiting_runs_in_tx
from app.tenant_models.operations import Cliente, Conversation, Message
from app.tenant_models.phase6_extensions import VoiceCallSegment, VoiceCallSession


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Voice timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _require_voice_ready(db: Session, tenant: TenantContext) -> None:
    inspector = inspect(db.connection())
    existing = set(inspector.get_table_names(schema=tenant.schema_name))
    if not {VoiceCallSession.__tablename__, VoiceCallSegment.__tablename__}.issubset(existing):
        raise HTTPException(status_code=503, detail="Voice call schema is unavailable")


def _segment_to_dict(seg: VoiceCallSegment) -> dict[str, Any]:
    return {
        "id": seg.id,
        "call_id": seg.call_id,
        "sequence_no": seg.sequence_no,
        "speaker": seg.speaker,
        "transcript": seg.transcript,
        "message_id": seg.message_id,
        "started_ms": seg.started_ms,
        "ended_ms": seg.ended_ms,
        "is_barge_in": seg.is_barge_in,
        "created_at": seg.created_at,
    }


def _call_to_dict(call: VoiceCallSession, segments: list[VoiceCallSegment] | None = None) -> dict[str, Any]:
    return {
        "id": call.id,
        "provider": call.provider,
        "external_call_id": call.external_call_id,
        "direction": call.direction,
        "from_number": call.from_number,
        "to_number": call.to_number,
        "client_id": call.client_id,
        "conversation_id": call.conversation_id,
        "agent_revision_id": call.agent_revision_id,
        "status": call.status,
        "billable_seconds": call.billable_seconds,
        "estimated_cost_usd": str(call.estimated_cost_usd),
        "recording_consent": call.recording_consent,
        "recording_attachment_id": call.recording_attachment_id,
        "barge_in_count": call.barge_in_count,
        "close_reason": call.close_reason,
        "started_at": call.started_at,
        "ended_at": call.ended_at,
        "created_at": call.created_at,
        "updated_at": call.updated_at,
        "segments": [_segment_to_dict(seg) for seg in (segments or [])],
    }


def _start_or_get_call_in_tx(
    db: Session,
    tenant: TenantContext,
    payload: VoiceCallCreateIn,
    *,
    now: datetime,
) -> tuple[VoiceCallSession, bool]:
    existing = db.scalar(
        select(VoiceCallSession)
        .where(
            VoiceCallSession.provider == payload.provider,
            VoiceCallSession.external_call_id == payload.external_call_id.strip(),
        )
        .with_for_update()
    )
    if existing is not None:
        return existing, True

    peer_number = payload.from_number.strip() if payload.direction == "inbound" else payload.to_number.strip()
    scoped_session = f"voice:{payload.provider}:{payload.external_call_id.strip()}"[:160]

    client_id = payload.client_id
    if client_id is None:
        client = db.scalar(select(Cliente).where(Cliente.telefono == peer_number))
        if client is None:
            client = Cliente(
                rut=f"vo:{payload.provider[:4]}:{payload.external_call_id.strip()}"[:64],
                nombre=f"Voz {peer_number}",
                telefono=peer_number[:40],
                whatsapp_id=scoped_session,
                canal_origen="voice",
                consentimiento_datos=bool(payload.recording_consent),
                fecha_consentimiento=now if payload.recording_consent else None,
            )
            db.add(client)
            db.flush()
        client_id = client.id

    get_or_create_initial_lead(db, client_id)

    conversation_id = payload.conversation_id
    if conversation_id is None:
        conv = Conversation(
            session_id=scoped_session,
            message={"channel": "voice", "provider": payload.provider, "external_call_id": payload.external_call_id},
        )
        db.add(conv)
        db.flush()
        conversation_id = conv.id

    call = VoiceCallSession(
        provider=payload.provider,
        external_call_id=payload.external_call_id.strip()[:160],
        direction=payload.direction,
        from_number=payload.from_number.strip()[:40],
        to_number=payload.to_number.strip()[:40],
        client_id=client_id,
        conversation_id=conversation_id,
        agent_revision_id=payload.agent_revision_id,
        status="in_progress",
        recording_consent=bool(payload.recording_consent),
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(call)
    db.flush()
    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="voice.call.started",
        aggregate_type="voice_call",
        aggregate_id=call.id,
        payload={
            "call_id": call.id,
            "provider": call.provider,
            "external_call_id": call.external_call_id,
            "client_id": call.client_id,
            "conversation_id": call.conversation_id,
        },
        occurred_at=now,
    )
    return call, False


def list_voice_calls(db: Session, tenant: TenantContext, *, limit: int = 50) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    _require_voice_ready(db, tenant)
    calls = list(
        db.scalars(select(VoiceCallSession).order_by(VoiceCallSession.id.desc()).limit(max(1, min(limit, 200)))).all()
    )
    return [_call_to_dict(c) for c in calls]


def get_voice_call(db: Session, tenant: TenantContext, call_id: int) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    _require_voice_ready(db, tenant)
    call = db.get(VoiceCallSession, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Voice call session not found")
    segs = list(
        db.scalars(
            select(VoiceCallSegment)
            .where(VoiceCallSegment.call_id == call_id)
            .order_by(VoiceCallSegment.sequence_no.asc())
        ).all()
    )
    return _call_to_dict(call, segs)


def start_voice_call(
    db: Session,
    tenant: TenantContext,
    payload: VoiceCallCreateIn,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_voice_ready(db, tenant)
    call, duplicate = _start_or_get_call_in_tx(db, tenant, payload, now=current)
    db.commit()
    db.refresh(call)
    res = _call_to_dict(call)
    res["duplicate"] = duplicate
    return res


def append_voice_segment(
    db: Session,
    tenant: TenantContext,
    call_id: int,
    payload: VoiceCallSegmentIn,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_voice_ready(db, tenant)
    call = db.scalar(select(VoiceCallSession).where(VoiceCallSession.id == call_id).with_for_update())
    if call is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Voice call session not found")

    existing_seg = db.scalar(
        select(VoiceCallSegment).where(
            VoiceCallSegment.call_id == call_id,
            VoiceCallSegment.sequence_no == payload.sequence_no,
        )
    )
    if existing_seg is not None:
        res = _segment_to_dict(existing_seg)
        res["duplicate"] = True
        db.rollback()
        return res

    thread_key = f"voice:{call.provider}:{call.external_call_id}"[:160]
    if call.conversation_id is not None:
        conv = db.get(Conversation, call.conversation_id)
        if conv is not None:
            thread_key = conv.session_id

    is_caller = payload.speaker == "caller"
    msg = Message(
        whatsapp_id=thread_key,
        rol="usuario" if is_caller else "agente",
        mensaje=payload.transcript.strip(),
        creado_en=current,
        connection_id=f"voice:{call.provider}",
        channel="voice",
        external_message_id=f"voice-seg:{call.id}:{payload.sequence_no}",
        direction="inbound" if is_caller else "outbound",
        message_type="audio_transcript",
        delivery_status="received" if is_caller else "delivered",
    )
    db.add(msg)
    db.flush()

    seg = VoiceCallSegment(
        call_id=call.id,
        sequence_no=payload.sequence_no,
        speaker=payload.speaker,
        transcript=payload.transcript.strip(),
        message_id=msg.id,
        started_ms=payload.started_ms,
        ended_ms=payload.ended_ms,
        is_barge_in=payload.is_barge_in,
        created_at=current,
    )
    db.add(seg)
    if payload.is_barge_in:
        call.barge_in_count = int(call.barge_in_count) + 1
    call.updated_at = current

    if is_caller and call.client_id is not None:
        cancel_waiting_runs_in_tx(
            db,
            tenant,
            event_type="message.inbound.received",
            contact_id=call.client_id,
            conversation_id=call.conversation_id,
            reason="caller_spoke",
            now=current,
        )

    db.commit()
    db.refresh(seg)
    res = _segment_to_dict(seg)
    res["duplicate"] = False
    return res


def transfer_voice_call(
    db: Session,
    tenant: TenantContext,
    call_id: int,
    payload: VoiceCallTransferIn,
    *,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_voice_ready(db, tenant)
    call = db.scalar(select(VoiceCallSession).where(VoiceCallSession.id == call_id).with_for_update())
    if call is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Voice call session not found")

    call.status = "transferred"
    call.close_reason = payload.reason.strip()[:120]
    call.ended_at = call.ended_at or current
    call.updated_at = current

    if call.conversation_id is not None:
        mark_waiting_human_in_tx(
            db,
            tenant,
            call.conversation_id,
            actor_user_id=actor_user_id,
            reason=f"voice_transfer:{call.close_reason}",
            now=current,
        )

    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="voice.call.transferred",
        aggregate_type="voice_call",
        aggregate_id=call.id,
        payload={"call_id": call.id, "reason": call.close_reason, "conversation_id": call.conversation_id},
        occurred_at=current,
    )
    db.commit()
    db.refresh(call)
    return _call_to_dict(call)


def complete_voice_call(
    db: Session,
    tenant: TenantContext,
    call_id: int,
    payload: VoiceCallCompleteIn,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_voice_ready(db, tenant)
    call = db.scalar(select(VoiceCallSession).where(VoiceCallSession.id == call_id).with_for_update())
    if call is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Voice call session not found")

    if payload.recording_attachment_id is not None and not call.recording_consent:
        db.rollback()
        raise HTTPException(status_code=422, detail="Recording attachment requires prior caller recording consent")

    try:
        cost = Decimal(payload.estimated_cost_usd.strip() or "0")
    except (InvalidOperation, ValueError):
        db.rollback()
        raise HTTPException(status_code=422, detail="Invalid estimated_cost_usd decimal") from None
    if cost < 0:
        db.rollback()
        raise HTTPException(status_code=422, detail="estimated_cost_usd cannot be negative")

    call.status = payload.status
    call.billable_seconds = payload.billable_seconds
    call.estimated_cost_usd = cost
    call.recording_attachment_id = payload.recording_attachment_id
    call.close_reason = payload.close_reason.strip()[:120] if payload.close_reason else call.close_reason
    call.ended_at = call.ended_at or current
    call.updated_at = current

    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="voice.call.completed",
        aggregate_type="voice_call",
        aggregate_id=call.id,
        payload={
            "call_id": call.id,
            "status": call.status,
            "billable_seconds": call.billable_seconds,
            "estimated_cost_usd": str(call.estimated_cost_usd),
        },
        occurred_at=current,
    )
    db.commit()
    db.refresh(call)
    return _call_to_dict(call)


def ingest_twilio_voice_webhook(
    db: Session,
    *,
    raw_body: bytes,
    signature_header: str | None,
    payload: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    account_sid = str(payload.get("AccountSid") or "").strip()
    call_sid = str(payload.get("CallSid") or "").strip()
    if not account_sid or not call_sid:
        raise HTTPException(status_code=422, detail="AccountSid and CallSid are required")

    route = db.scalar(
        select(PublicChannelWebhookRoute).where(
            PublicChannelWebhookRoute.channel == "voice_twilio",
            PublicChannelWebhookRoute.external_account_id == account_sid,
            PublicChannelWebhookRoute.is_active.is_(True),
        )
    )
    if route is None:
        raise HTTPException(status_code=404, detail="Twilio voice webhook route not found or inactive")

    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing Twilio X-Twilio-Signature-256 header")
    expected = "sha256=" + hmac.new(route.app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header.strip()):
        raise HTTPException(status_code=401, detail="Invalid Twilio webhook signature")

    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == route.auth_tenant_id))
    if runtime is None:
        raise HTTPException(status_code=404, detail="Tenant runtime not provisioned")
    ensure_runtime_is_usable(runtime)
    tenant = TenantContext(
        auth_tenant_id=runtime.auth_tenant_id,
        tenant_slug=runtime.tenant_slug,
        schema_name=runtime.schema_name,
        tenant_code=runtime.tenant_code,
        plan=runtime.plan,
        status=runtime.status,
    )

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_voice_ready(db, tenant)

    raw_dir = str(payload.get("Direction") or "inbound").lower()
    direction = "outbound" if "outbound" in raw_dir else "inbound"
    call, _ = _start_or_get_call_in_tx(
        db,
        tenant,
        VoiceCallCreateIn(
            provider="twilio",
            external_call_id=call_sid,
            direction=direction,
            from_number=str(payload.get("From") or "unknown")[:40],
            to_number=str(payload.get("To") or "unknown")[:40],
            recording_consent=bool(payload.get("RecordingConsent", False)),
        ),
        now=current,
    )

    raw_status = str(payload.get("CallStatus") or "in-progress").strip().lower()
    status_map = {
        "ringing": "ringing",
        "in-progress": "in_progress",
        "completed": "completed",
        "no-answer": "no_answer",
        "busy": "failed",
        "failed": "failed",
        "canceled": "failed",
    }
    mapped_status = status_map.get(raw_status, "in_progress")
    call.status = mapped_status
    if payload.get("CallDuration") is not None:
        call.billable_seconds = max(0, int(payload["CallDuration"]))
    if mapped_status in ("completed", "no_answer", "voicemail", "failed"):
        call.ended_at = call.ended_at or current
    call.updated_at = current

    db.commit()
    db.refresh(call)
    return _call_to_dict(call)
