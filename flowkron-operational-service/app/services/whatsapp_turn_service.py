from datetime import datetime, timedelta, timezone
import hmac
import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.whatsapp_turn import TurnClaimIn, TurnCompleteIn, TurnPrepareIn, TurnReceiptIn
from app.services.ingest_service import _mark_message_processed, ingest_whatsapp_message
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.operations import Cliente, Lead, Message
from app.tenant_models.whatsapp_turn import WhatsAppTurn


LEASE_SECONDS = 180  # longer than the connector's bounded agent request


def _now():
    return datetime.now(timezone.utc)


def _load(db: Session, tenant: TenantContext, turn_id: int) -> WhatsAppTurn:
    bind_tenant_session(db, tenant.schema_name)
    turn = db.scalar(select(WhatsAppTurn).where(WhatsAppTurn.id == turn_id).with_for_update())
    if not turn:
        raise HTTPException(status_code=404, detail="Turn not found")
    return turn


def _snapshot(turn: WhatsAppTurn, message: Message, *, claimed=False):
    return {
        "turn_id": turn.id, "state": turn.state, "claimed": claimed,
        "claim_token": turn.claim_token if claimed else None,
        "lease_until": turn.lease_until, "input_body": message.mensaje,
        "phone": turn.phone, "external_thread_id": message.whatsapp_id,
        "reply_body": turn.reply_body, "requires_human": turn.requires_human,
        "outbound_message_id": turn.outbound_message_id, "last_error": turn.last_error,
    }


def _finish(db, turn, *, claimed=False):
    turn.updated_at = _now()
    result = _snapshot(turn, db.get(Message, turn.id), claimed=claimed)
    db.commit()
    return result


def _check_token(turn, token, *, allow_expired=False):
    if not turn.claim_token or not hmac.compare_digest(turn.claim_token, token):
        raise HTTPException(status_code=409, detail="Stale turn claim")
    if not allow_expired and (not turn.lease_until or turn.lease_until <= _now()):
        raise HTTPException(status_code=409, detail="Turn claim expired")


def _check_consent(db, turn):
    accepted = db.scalar(select(Cliente.consentimiento_datos).where(Cliente.whatsapp_id == turn.phone))
    if accepted is not True:
        turn.state = "cancelled"
        turn.last_error = "consent_withdrawn"
        turn.lease_until = None
        return False
    return True


def claim_turn(db: Session, tenant: TenantContext, payload: TurnClaimIn) -> dict:
    # New entry and turn are committed together. Older messages without a turn
    # are not assumed safe to resend, even when they have no recorded reply.
    stored = ingest_whatsapp_message(db, tenant, payload, create_turn=True)
    if stored["message_id"] is None:
        return {"state": "legacy_untracked"}
    bind_tenant_session(db, tenant.schema_name)
    turn = db.scalar(select(WhatsAppTurn).where(WhatsAppTurn.id == stored["message_id"]).with_for_update())
    if not turn:
        db.commit()
        return {"turn_id": stored["message_id"], "state": "legacy_untracked"}
    if turn.phone != payload.phone:
        raise HTTPException(status_code=409, detail="Turn belongs to another contact")
    if turn.state in {"completed", "unknown", "cancelled"}:
        return _finish(db, turn)
    if turn.state == "sending":
        if turn.lease_until <= _now():
            turn.state = "unknown"
            turn.last_error = "send_outcome_unknown"
        return _finish(db, turn)
    if not _check_consent(db, turn):
        return _finish(db, turn)
    if turn.lease_until and turn.lease_until > _now():
        return _finish(db, turn)
    turn.claim_token = secrets.token_urlsafe(32)
    turn.lease_until = _now() + timedelta(seconds=LEASE_SECONDS)
    turn.state = "prepared" if turn.reply_body is not None else "generating"
    turn.last_error = None
    return _finish(db, turn, claimed=True)


def prepare_turn(db: Session, tenant: TenantContext, turn_id: int, payload: TurnPrepareIn) -> dict:
    turn = _load(db, tenant, turn_id)
    _check_token(turn, payload.claim_token)
    if turn.state == "prepared":
        if turn.reply_body != payload.reply_body or turn.requires_human != payload.requires_human:
            raise HTTPException(status_code=409, detail="Prepared reply is immutable")
        return _finish(db, turn)
    if turn.state != "generating":
        raise HTTPException(status_code=409, detail="Turn is not generating")
    if not _check_consent(db, turn):
        return _finish(db, turn)
    turn.reply_body = payload.reply_body
    turn.requires_human = payload.requires_human
    turn.state = "prepared"
    turn.lease_until = _now() + timedelta(seconds=LEASE_SECONDS)
    if payload.requires_human:
        lead = db.get(Lead, turn.lead_id)
        lead.estado = "en_proceso"
        lead.estado_seguimiento = "requiere_humano"
        create_system_event(db, "whatsapp.turn.handoff", tenant.auth_tenant_id, tenant.schema_name, {"turn_id": turn.id})
    create_system_event(db, "whatsapp.turn.prepared", tenant.auth_tenant_id, tenant.schema_name, {"turn_id": turn.id})
    return _finish(db, turn)


def begin_turn_send(db: Session, tenant: TenantContext, turn_id: int, token: str) -> dict:
    turn = _load(db, tenant, turn_id)
    _check_token(turn, token)
    # Repeating this request never grants another send, including a response
    # lost after commit. Only the first successful transition grants permission.
    if turn.state != "prepared":
        raise HTTPException(status_code=409, detail="Send already started or turn unavailable")
    if not _check_consent(db, turn):
        return _finish(db, turn)
    turn.state = "sending"
    turn.lease_until = _now() + timedelta(seconds=LEASE_SECONDS)
    return _finish(db, turn, claimed=True)


def complete_turn(db: Session, tenant: TenantContext, turn_id: int, payload: TurnCompleteIn, *, reconciled=False) -> dict:
    turn = _load(db, tenant, turn_id)
    return _complete_locked(db, tenant, turn, payload, reconciled=reconciled)


def _complete_locked(db, tenant, turn, payload, *, reconciled=False):
    # Late acknowledgement from the original sender may resolve an expired
    # attempt. A new claimant never receives this token while outcome is unknown.
    _check_token(turn, payload.claim_token, allow_expired=True)
    if turn.state == "completed":
        outbound = db.get(Message, turn.outbound_message_id)
        if outbound.provider_message_id != payload.provider_message_id:
            raise HTTPException(status_code=409, detail="Different provider acknowledgement")
        return _finish(db, turn)
    if turn.state not in {"sending", "unknown"}:
        raise HTTPException(status_code=409, detail="Send has not started")
    incoming = db.get(Message, turn.id)
    external_id = f"flowkron:turn:{turn.id}:reply"
    outbound = Message(
        whatsapp_id=incoming.whatsapp_id, rol="agente", mensaje=turn.reply_body,
        creado_en=payload.sent_at, connection_id=incoming.connection_id, channel=incoming.channel,
        external_message_id=external_id, provider_message_id=payload.provider_message_id,
        direction="outbound", message_type="text", delivery_status="sent",
    )
    db.add(outbound)
    db.flush()
    _mark_message_processed(db, external_id)
    turn.outbound_message_id = outbound.id
    turn.state = "completed"
    turn.last_error = None
    turn.lease_until = None
    event = "whatsapp.turn.reconciled" if reconciled else "whatsapp.turn.completed"
    create_system_event(db, event, tenant.auth_tenant_id, tenant.schema_name, {"turn_id": turn.id, "message_id": outbound.id})
    return _finish(db, turn)


def reconcile_turn(db: Session, tenant: TenantContext, turn_id: int, payload: TurnReceiptIn) -> dict:
    """Record an externally verified receipt; never grants permission to resend.

    Restricted to existing tenant-scoped ingest credentials. This endpoint does
    not query the provider: the operator must verify the original send first.
    """
    turn = _load(db, tenant, turn_id)
    if turn.state == "sending" and turn.lease_until <= _now():
        turn.state = "unknown"
    if turn.state not in {"unknown", "completed"}:
        raise HTTPException(status_code=409, detail="Only an unknown send can be reconciled")
    receipt = TurnCompleteIn(claim_token=turn.claim_token, **payload.model_dump())
    return _complete_locked(db, tenant, turn, receipt, reconciled=True)


def release_turn(db: Session, tenant: TenantContext, turn_id: int, token: str) -> dict:
    turn = _load(db, tenant, turn_id)
    _check_token(turn, token, allow_expired=True)
    if turn.state in {"generating", "prepared"}:
        turn.state = "prepared" if turn.reply_body is not None else "received"
        turn.lease_until = None
        turn.last_error = "generation_or_persistence_failed"
    elif turn.state == "sending":
        turn.state = "unknown"
        turn.last_error = "send_outcome_unknown"
    return _finish(db, turn)


def read_turn(db: Session, tenant: TenantContext, turn_id: int) -> dict:
    turn = _load(db, tenant, turn_id)
    if turn.state == "sending" and turn.lease_until <= _now():
        turn.state = "unknown"
        turn.last_error = "send_outcome_unknown"
    return _finish(db, turn)
