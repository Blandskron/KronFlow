from datetime import datetime, timedelta, timezone
import hmac
import secrets

from fastapi import HTTPException
from sqlalchemy import and_, func, inspect, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from app.core.tenant_resolver import TenantContext
from app.schemas.whatsapp_turn import ProviderReceiptIn, TurnClaimIn, TurnCompleteIn, TurnEnqueueIn, TurnPrepareIn, TurnReceiptIn
from app.services.conversation_control_service import is_ai_permitted_for_conversation_in_tx
from app.services.ingest_service import (
    RECOVERABLE_TURN_STATES, TURN_JOB_ATTEMPT_LIMIT, _mark_message_processed, ingest_whatsapp_message,
    lock_turn_jobs, require_turn_job_capacity,
)
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.operations import Cliente, Lead, Message
from app.tenant_models.whatsapp_turn import WhatsAppSendEvidence, WhatsAppTurn, WhatsAppTurnJob


LEASE_SECONDS = 180  # longer than the connector's bounded agent request
EVIDENCE_PRIORITY = {"unknown": 0, "sent": 1, "failed": 2, "delivered": 3, "read": 4}


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


def _check_ai_control(db: Session, tenant: TenantContext, turn: WhatsAppTurn, *, allow_handoff_send: bool = False) -> bool:
    permitted, reason = is_ai_permitted_for_conversation_in_tx(db, tenant, turn.conversation_id)
    if permitted:
        return True
    if allow_handoff_send and turn.requires_human and reason == "control_waiting_human":
        return True
    turn.state = "cancelled"
    turn.last_error = (reason or "ai_not_permitted")[:64]
    turn.lease_until = None
    return False


def turn_jobs_ready(db: Session, tenant: TenantContext) -> bool:
    return inspect(db.connection()).has_table(WhatsAppTurnJob.__tablename__, schema=tenant.schema_name)


def turn_receipts_ready(db: Session, tenant: TenantContext) -> bool:
    return inspect(db.connection()).has_table(WhatsAppSendEvidence.__tablename__, schema=tenant.schema_name)


def _get_job(db, tenant, turn_id):
    if turn_jobs_ready(db, tenant):
        return db.get(WhatsAppTurnJob, turn_id)
    return None


def _start_claim(turn, now):
    turn.claim_token = secrets.token_urlsafe(32)
    turn.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    turn.state = "prepared" if turn.reply_body is not None else "generating"
    turn.last_error = None


def enqueue_turn(db: Session, tenant: TenantContext, payload: TurnEnqueueIn) -> dict:
    if not turn_jobs_ready(db, tenant):
        raise HTTPException(status_code=503, detail="WhatsApp durable queue schema is unavailable")
    message = TurnClaimIn(**payload.model_dump(exclude={"account_key", "recipient_jid"}))
    job = WhatsAppTurnJob(account_key=payload.account_key, recipient_jid=payload.recipient_jid)
    stored = ingest_whatsapp_message(db, tenant, message, job=job)
    turn_id = stored["message_id"]
    if not stored["duplicate"]:
        return {"turn_id": turn_id, "disposition": "accepted"}
    existing = db.get(WhatsAppTurnJob, turn_id) if turn_id is not None else None
    if existing is not None and existing.account_key != payload.account_key:
        raise HTTPException(status_code=409, detail="Turn belongs to another WhatsApp account")
    return {"turn_id": turn_id, "disposition": "duplicate" if existing else "legacy_untracked"}


def claim_next_turn(db: Session, tenant: TenantContext, account_key: str) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    if not turn_jobs_ready(db, tenant):
        raise HTTPException(status_code=503, detail="WhatsApp durable queue schema is unavailable")
    lock_turn_jobs(db, tenant)
    now = _now()
    older, older_job = aliased(WhatsAppTurn), aliased(WhatsAppTurnJob)
    has_predecessor = select(older.id).join(older_job, older_job.turn_id == older.id).where(
        older.phone == WhatsAppTurn.phone,
        older.id != WhatsAppTurn.id,
        older_job.account_key == account_key,
        older.state.in_((*RECOVERABLE_TURN_STATES, "sending")),
        or_(
            older.lease_until > now,
            and_(older.id < WhatsAppTurn.id, older_job.attempts < TURN_JOB_ATTEMPT_LIMIT),
        ),
    ).exists()
    result = db.execute(select(WhatsAppTurn, WhatsAppTurnJob).join(WhatsAppTurnJob).where(
        WhatsAppTurnJob.account_key == account_key,
        or_(WhatsAppTurn.lease_until.is_(None), WhatsAppTurn.lease_until <= now),
        or_(
            WhatsAppTurn.state == "sending",
            WhatsAppTurn.state.in_(RECOVERABLE_TURN_STATES)
            & (WhatsAppTurnJob.attempts < TURN_JOB_ATTEMPT_LIMIT)
            & (WhatsAppTurnJob.available_at <= now)
            & ~has_predecessor,
            WhatsAppTurn.state.in_(RECOVERABLE_TURN_STATES)
            & (WhatsAppTurnJob.attempts >= TURN_JOB_ATTEMPT_LIMIT)
            & WhatsAppTurn.last_error.is_distinct_from("attempt_limit_reached"),
        ),
    ).order_by(WhatsAppTurn.id).limit(1).with_for_update(of=WhatsAppTurn, skip_locked=True)).first()
    if result is None:
        db.commit()
        return {"job": None}
    turn, job = result
    if turn.state == "sending":
        turn.state = "unknown"
        turn.last_error = "send_outcome_unknown"
        _finish(db, turn)
        return {"job": None}
    if job.attempts >= TURN_JOB_ATTEMPT_LIMIT:
        turn.state = "prepared" if turn.reply_body is not None else "received"
        turn.lease_until = None
        turn.last_error = "attempt_limit_reached"
        _finish(db, turn)
        return {"job": None}
    if not _check_consent(db, turn) or not _check_ai_control(db, tenant, turn, allow_handoff_send=turn.reply_body is not None):
        _finish(db, turn)
        return {"job": None}
    job.attempts += 1
    recipient_jid = job.recipient_jid
    _start_claim(turn, now)
    return {"job": {**_finish(db, turn, claimed=True), "recipient_jid": recipient_jid}}


def retry_turn_job(db: Session, tenant: TenantContext, turn_id: int, account_key: str) -> dict:
    lock_turn_jobs(db, tenant)
    turn = _load(db, tenant, turn_id)
    job = _get_job(db, tenant, turn_id)
    if job is None or job.account_key != account_key:
        raise HTTPException(status_code=404, detail="Turn job not found")
    now = _now()
    if (turn.state not in RECOVERABLE_TURN_STATES or job.attempts < TURN_JOB_ATTEMPT_LIMIT
            or (turn.lease_until and turn.lease_until > now)):
        raise HTTPException(status_code=409, detail="Only an exhausted recoverable turn can be retried")
    if not _check_consent(db, turn) or not _check_ai_control(db, tenant, turn):
        return _finish(db, turn)
    require_turn_job_capacity(db)
    job.attempts = 0
    job.available_at = now
    turn.state = "prepared" if turn.reply_body is not None else "received"
    turn.claim_token = None
    turn.lease_until = None
    turn.last_error = None
    create_system_event(db, "whatsapp.turn.requeued", tenant.auth_tenant_id, tenant.schema_name, {"turn_id": turn.id})
    return _finish(db, turn)


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
    if stored["duplicate"] and _get_job(db, tenant, turn.id) is not None:
        return _finish(db, turn)
    if turn.state in {"completed", "unknown", "cancelled"}:
        return _finish(db, turn)
    if turn.state == "sending":
        if turn.lease_until <= _now():
            turn.state = "unknown"
            turn.last_error = "send_outcome_unknown"
        return _finish(db, turn)
    if not _check_consent(db, turn) or not _check_ai_control(db, tenant, turn):
        return _finish(db, turn)
    if turn.lease_until and turn.lease_until > _now():
        return _finish(db, turn)
    _start_claim(turn, _now())
    return _finish(db, turn, claimed=True)


def prepare_turn(db: Session, tenant: TenantContext, turn_id: int, payload: TurnPrepareIn) -> dict:
    turn = _load(db, tenant, turn_id)
    _check_token(turn, payload.claim_token, allow_expired=turn.state == "cancelled")
    if turn.state == "cancelled":
        return _finish(db, turn)
    if turn.state == "prepared":
        if turn.reply_body != payload.reply_body or turn.requires_human != payload.requires_human:
            raise HTTPException(status_code=409, detail="Prepared reply is immutable")
        return _finish(db, turn)
    if turn.state != "generating":
        raise HTTPException(status_code=409, detail="Turn is not generating")
    if not _check_consent(db, turn) or not _check_ai_control(db, tenant, turn):
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


def begin_turn_send(
    db: Session, tenant: TenantContext, turn_id: int, token: str, provider_message_id: str | None = None,
) -> dict:
    turn = _load(db, tenant, turn_id)
    _check_token(turn, token, allow_expired=turn.state == "cancelled")
    if turn.state == "cancelled":
        return _finish(db, turn)
    # Repeating this request never grants another send, including a response
    # lost after commit. Only the first successful transition grants permission.
    if turn.state != "prepared":
        raise HTTPException(status_code=409, detail="Send already started or turn unavailable")
    if not _check_consent(db, turn) or not _check_ai_control(db, tenant, turn, allow_handoff_send=True):
        return _finish(db, turn)
    now = _now()
    if provider_message_id is not None:
        job = _get_job(db, tenant, turn_id)
        if job is None or not turn_receipts_ready(db, tenant):
            raise HTTPException(status_code=409, detail="Turn cannot reserve a provider identity")
        reservation = insert(WhatsAppSendEvidence).values(
            turn_id=turn_id, account_key=job.account_key, provider_message_id=provider_message_id, started_at=now,
        ).on_conflict_do_nothing().returning(WhatsAppSendEvidence.turn_id)
        if db.scalar(reservation) is None:
            raise HTTPException(status_code=409, detail="Provider message identity is already reserved")
    turn.state = "sending"
    turn.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    return _finish(db, turn, claimed=True)


def complete_turn(db: Session, tenant: TenantContext, turn_id: int, payload: TurnCompleteIn, *, reconciled=False) -> dict:
    turn = _load(db, tenant, turn_id)
    return _complete_locked(db, tenant, turn, payload, reconciled=reconciled)


def _complete_locked(db, tenant, turn, payload, *, reconciled=False, receipt=False):
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
    evidence = db.get(WhatsAppSendEvidence, turn.id) if turn_receipts_ready(db, tenant) else None
    if evidence is not None:
        if evidence.provider_message_id != payload.provider_message_id:
            raise HTTPException(status_code=409, detail="Different provider acknowledgement")
        if evidence.status == "unknown":
            evidence.status = "sent"
    incoming = db.get(Message, turn.id)
    external_id = f"flowkron:turn:{turn.id}:reply"
    outbound = Message(
        whatsapp_id=incoming.whatsapp_id, rol="agente", mensaje=turn.reply_body,
        creado_en=payload.sent_at, connection_id=incoming.connection_id, channel=incoming.channel,
        external_message_id=external_id, provider_message_id=payload.provider_message_id,
        direction="outbound", message_type="text", delivery_status=evidence.status if evidence else "sent",
    )
    db.add(outbound)
    db.flush()
    _mark_message_processed(db, external_id)
    turn.outbound_message_id = outbound.id
    turn.state = "completed"
    turn.last_error = None
    turn.lease_until = None
    if receipt:
        event = "whatsapp.turn.receipt_confirmed"
    else:
        event = "whatsapp.turn.reconciled" if reconciled else "whatsapp.turn.completed"
    create_system_event(db, event, tenant.auth_tenant_id, tenant.schema_name, {
        "turn_id": turn.id, "message_id": outbound.id, "delivery_status": outbound.delivery_status,
    })
    return _finish(db, turn)


def record_provider_receipts(db: Session, tenant: TenantContext, receipts: list[ProviderReceiptIn]) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    if not turn_receipts_ready(db, tenant):
        raise HTTPException(status_code=503, detail="WhatsApp provider receipt schema is unavailable")
    return {"applied": sum(_apply_provider_receipt(db, tenant, receipt) for receipt in receipts)}


def _apply_provider_receipt(db: Session, tenant: TenantContext, receipt: ProviderReceiptIn) -> bool:
    turn = db.scalar(
        select(WhatsAppTurn)
        .join(WhatsAppSendEvidence, WhatsAppSendEvidence.turn_id == WhatsAppTurn.id)
        .join(WhatsAppTurnJob, WhatsAppTurnJob.turn_id == WhatsAppTurn.id)
        .join(Message, Message.id == WhatsAppTurn.id)
        .where(
            WhatsAppSendEvidence.account_key == receipt.account_key,
            WhatsAppTurnJob.account_key == receipt.account_key,
            WhatsAppSendEvidence.provider_message_id == receipt.provider_message_id,
            Message.connection_id == receipt.connection_id,
            Message.channel == "whatsapp",
            or_(WhatsAppTurnJob.recipient_jid.in_(receipt.recipient_jids),
                func.concat(WhatsAppTurn.phone, "@s.whatsapp.net").in_(receipt.recipient_jids)),
            WhatsAppTurn.state.in_(("sending", "unknown", "completed")),
        ).with_for_update(of=WhatsAppTurn)
    )
    if turn is None:
        db.commit()
        return False
    evidence = db.get(WhatsAppSendEvidence, turn.id)
    if EVIDENCE_PRIORITY[receipt.status] <= EVIDENCE_PRIORITY[evidence.status]:
        db.commit()
        return False
    evidence.status = receipt.status
    evidence.failure_reason = (receipt.failure_reason or "provider_rejected") if receipt.status == "failed" else None
    if turn.state == "completed":
        outbound = db.get(Message, turn.outbound_message_id)
        outbound.delivery_status = receipt.status
        db.commit()
        return True
    # A matched channel event is enough to resolve the reserved send. If the
    # connector has no acknowledgement timestamp, use the recorded attempt start.
    completion = TurnCompleteIn(
        claim_token=turn.claim_token, provider_message_id=evidence.provider_message_id, sent_at=evidence.started_at,
    )
    _complete_locked(db, tenant, turn, completion, receipt=True)
    return True


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
        was_leased = turn.lease_until is not None
        turn.state = "prepared" if turn.reply_body is not None else "received"
        turn.lease_until = None
        if was_leased:
            turn.last_error = "generation_or_persistence_failed"
            job = _get_job(db, tenant, turn_id)
            if job is not None:
                job.available_at = _now() + timedelta(seconds=5 * 2 ** (job.attempts - 1))
                if job.attempts >= TURN_JOB_ATTEMPT_LIMIT:
                    turn.last_error = "attempt_limit_reached"
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
