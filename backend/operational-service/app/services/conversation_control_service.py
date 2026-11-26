"""Conversation HITL control (FK-06) and effective AI policy enforcement (FK-19)."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import inspect, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.tenant_runtime import TenantRuntime
from app.services.action_outbox_service import enqueue_outbox_action
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.ingest_service import RECOVERABLE_TURN_STATES
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.conversation_control import ConversationControl, ConversationControlEvent, TenantAIPolicy
from app.tenant_models.operations import Cliente, Conversation, Lead, Message
from app.tenant_models.whatsapp_turn import WhatsAppTurn


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Control timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def conversation_control_ready(db: Session, tenant: TenantContext) -> bool:
    inspector = inspect(db.connection())
    return (
        inspector.has_table(ConversationControl.__tablename__, schema=tenant.schema_name)
        and inspector.has_table(TenantAIPolicy.__tablename__, schema=tenant.schema_name)
    )


def _require_control_ready(db: Session, tenant: TenantContext) -> None:
    if not conversation_control_ready(db, tenant):
        raise HTTPException(status_code=503, detail="Conversation control schema is unavailable")


def _tenant_ai_enabled_in_tx(db: Session) -> bool:
    policy = db.get(TenantAIPolicy, 1)
    return True if policy is None else bool(policy.ai_enabled)


def is_ai_permitted_for_conversation_in_tx(
    db: Session, tenant: TenantContext, conversation_id: int,
) -> tuple[bool, str | None]:
    """Check runtime status, tenant AI policy, and conversation control in an already-bound session."""
    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == tenant.auth_tenant_id))
    if runtime is not None and runtime.status != "active":
        return False, "tenant_suspended"
    if not conversation_control_ready(db, tenant):
        return True, None
    if not _tenant_ai_enabled_in_tx(db):
        return False, "tenant_ai_disabled"
    control = db.get(ConversationControl, conversation_id)
    if control is None:
        return True, None
    if not control.ai_enabled:
        return False, "conversation_ai_disabled"
    if control.mode != "ai_active":
        return False, f"control_{control.mode}"
    return True, None


def _cancel_recoverable_ai_turns_in_tx(
    db: Session, tenant: TenantContext, *, reason: str, now: datetime, conversation_id: int | None = None,
) -> int:
    """Invalidate pending AI turns (never touching turns already in `sending` or `completed`)."""
    if not inspect(db.connection()).has_table(WhatsAppTurn.__tablename__, schema=tenant.schema_name):
        return 0
    stmt = (
        update(WhatsAppTurn)
        .where(WhatsAppTurn.state.in_(RECOVERABLE_TURN_STATES))
        .values(state="cancelled", last_error=reason[:64], lease_until=None, updated_at=now)
    )
    if conversation_id is not None:
        stmt = stmt.where(WhatsAppTurn.conversation_id == conversation_id)
    result = db.execute(stmt)
    return int(result.rowcount or 0)


def _ensure_and_lock_control(db: Session, conversation_id: int, now: datetime) -> tuple[Conversation, ConversationControl]:
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id).with_for_update())
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.execute(
        insert(ConversationControl)
        .values(
            conversation_id=conversation_id,
            mode="ai_active",
            ai_enabled=True,
            control_version=1,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["conversation_id"])
    )
    control = db.scalar(
        select(ConversationControl).where(ConversationControl.conversation_id == conversation_id).with_for_update()
    )
    return conversation, control


def _control_snapshot(control: ConversationControl, *, tenant_ai_enabled: bool, cancelled_turns: int = 0) -> dict:
    return {
        "conversation_id": control.conversation_id,
        "mode": control.mode,
        "owner_user_id": control.owner_user_id,
        "ai_enabled": control.ai_enabled,
        "tenant_ai_enabled": tenant_ai_enabled,
        "control_version": control.control_version,
        "handoff_reason": control.handoff_reason,
        "resolution_reason": control.resolution_reason,
        "updated_by": control.updated_by,
        "updated_at": control.updated_at,
        "cancelled_ai_turns": cancelled_turns,
    }


def _record_transition(
    db: Session,
    tenant: TenantContext,
    control: ConversationControl,
    *,
    from_mode: str,
    to_mode: str,
    actor_user_id: str | None,
    reason: str | None,
    event_type: str,
    now: datetime,
) -> None:
    db.add(
        ConversationControlEvent(
            conversation_id=control.conversation_id,
            from_mode=from_mode,
            to_mode=to_mode,
            control_version=control.control_version,
            actor_user_id=actor_user_id,
            owner_user_id=control.owner_user_id,
            reason=reason,
            created_at=now,
        )
    )
    create_system_event(
        db,
        event_type,
        tenant.auth_tenant_id,
        tenant.schema_name,
        {
            "conversation_id": control.conversation_id,
            "from_mode": from_mode,
            "to_mode": to_mode,
            "control_version": control.control_version,
            "actor_user_id": actor_user_id,
            "owner_user_id": control.owner_user_id,
            "reason": reason,
        },
    )
    domain_event_type = "conversation.resolved" if to_mode == "resolved" else event_type
    if domain_event_type in ("conversation.handoff.requested", "conversation.claimed", "conversation.resolved"):
        publish_domain_event_in_tx(
            db,
            tenant,
            event_type=domain_event_type,
            aggregate_type="conversation",
            aggregate_id=control.conversation_id,
            payload={
                "conversation_id": control.conversation_id,
                "from_mode": from_mode,
                "to_mode": to_mode,
                "owner_user_id": control.owner_user_id,
                "reason": reason,
            },
            occurred_at=now,
        )


def get_conversation_control(db: Session, tenant: TenantContext, conversation_id: int) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    _require_control_ready(db, tenant)
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    control = db.get(ConversationControl, conversation_id)
    tenant_ai = _tenant_ai_enabled_in_tx(db)
    if control is None:
        return {
            "conversation_id": conversation_id,
            "mode": "ai_active",
            "owner_user_id": None,
            "ai_enabled": True,
            "tenant_ai_enabled": tenant_ai,
            "control_version": 1,
            "handoff_reason": None,
            "resolution_reason": None,
            "updated_by": None,
            "updated_at": conversation.creado_en,
            "cancelled_ai_turns": 0,
        }
    return _control_snapshot(control, tenant_ai_enabled=tenant_ai)


def set_tenant_ai_policy(
    db: Session,
    tenant: TenantContext,
    *,
    ai_enabled: bool,
    actor_user_id: str,
    reason: str | None = None,
    now: datetime | None = None,
) -> dict:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_control_ready(db, tenant)
    clean_reason = reason.strip()[:180] if reason else None
    db.execute(
        insert(TenantAIPolicy)
        .values(id=1, ai_enabled=bool(ai_enabled), updated_by=actor_user_id[:64], reason=clean_reason, updated_at=current)
        .on_conflict_do_update(
            index_elements=["id"],
            set_={
                "ai_enabled": bool(ai_enabled),
                "updated_by": actor_user_id[:64],
                "reason": clean_reason,
                "updated_at": current,
            },
        )
    )
    cancelled = 0
    if not ai_enabled:
        cancelled = _cancel_recoverable_ai_turns_in_tx(db, tenant, reason="tenant_ai_disabled", now=current)
    create_system_event(
        db,
        "tenant.ai_policy.changed",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"ai_enabled": bool(ai_enabled), "actor_user_id": actor_user_id, "reason": clean_reason, "cancelled_ai_turns": cancelled},
    )
    db.commit()
    return {
        "ai_enabled": bool(ai_enabled),
        "updated_by": actor_user_id[:64],
        "reason": clean_reason,
        "updated_at": current,
        "cancelled_ai_turns": cancelled,
    }


def mark_waiting_human_in_tx(
    db: Session,
    tenant: TenantContext,
    conversation_id: int,
    *,
    actor_user_id: str | None,
    reason: str,
    now: datetime,
) -> ConversationControl | None:
    """Internal helper for agent handoff inside an existing transaction."""
    if not conversation_control_ready(db, tenant):
        return None
    _, control = _ensure_and_lock_control(db, conversation_id, now)
    if control.mode != "ai_active":
        return control
    from_mode = control.mode
    control.mode = "waiting_human"
    control.owner_user_id = None
    control.handoff_reason = reason.strip()[:180] or "handoff_requested"
    control.control_version += 1
    control.updated_by = actor_user_id[:64] if actor_user_id else None
    control.updated_at = now
    _record_transition(
        db,
        tenant,
        control,
        from_mode=from_mode,
        to_mode="waiting_human",
        actor_user_id=actor_user_id,
        reason=control.handoff_reason,
        event_type="conversation.handoff.requested",
        now=now,
    )
    return control


def request_handoff(
    db: Session,
    tenant: TenantContext,
    conversation_id: int,
    *,
    actor_user_id: str,
    reason: str,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> dict:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_control_ready(db, tenant)
    _, control = _ensure_and_lock_control(db, conversation_id, current)
    if expected_version is not None and control.control_version != expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale conversation control version")
    if control.mode != "ai_active":
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Cannot request handoff from mode '{control.mode}'")
    from_mode = control.mode
    control.mode = "waiting_human"
    control.owner_user_id = None
    control.handoff_reason = reason.strip()[:180] or "handoff_requested"
    control.control_version += 1
    control.updated_by = actor_user_id[:64]
    control.updated_at = current
    cancelled = _cancel_recoverable_ai_turns_in_tx(
        db, tenant, reason="control_waiting_human", now=current, conversation_id=conversation_id,
    )
    _record_transition(
        db,
        tenant,
        control,
        from_mode=from_mode,
        to_mode="waiting_human",
        actor_user_id=actor_user_id,
        reason=control.handoff_reason,
        event_type="conversation.handoff.requested",
        now=current,
    )
    tenant_ai = _tenant_ai_enabled_in_tx(db)
    db.commit()
    db.refresh(control)
    return _control_snapshot(control, tenant_ai_enabled=tenant_ai, cancelled_turns=cancelled)


def claim_conversation(
    db: Session,
    tenant: TenantContext,
    conversation_id: int,
    *,
    actor_user_id: str,
    expected_version: int,
    is_supervisor: bool = False,
    reason: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Compare-and-swap claim ensuring a single active human actor owns the conversation."""
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_control_ready(db, tenant)
    _, control = _ensure_and_lock_control(db, conversation_id, current)
    if control.control_version != expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale conversation control version")
    if control.mode == "resolved":
        db.rollback()
        raise HTTPException(status_code=409, detail="Cannot claim a resolved conversation")
    if control.mode == "human_active":
        if control.owner_user_id == actor_user_id:
            tenant_ai = _tenant_ai_enabled_in_tx(db)
            db.commit()
            return _control_snapshot(control, tenant_ai_enabled=tenant_ai)
        if not is_supervisor:
            db.rollback()
            raise HTTPException(status_code=409, detail="Conversation is already claimed by another operator")

    from_mode = control.mode
    control.mode = "human_active"
    control.owner_user_id = actor_user_id[:64]
    control.control_version += 1
    control.updated_by = actor_user_id[:64]
    control.updated_at = current
    cancelled = _cancel_recoverable_ai_turns_in_tx(
        db, tenant, reason="control_human_active", now=current, conversation_id=conversation_id,
    )
    _record_transition(
        db,
        tenant,
        control,
        from_mode=from_mode,
        to_mode="human_active",
        actor_user_id=actor_user_id,
        reason=reason.strip()[:180] if reason else None,
        event_type="conversation.claimed",
        now=current,
    )
    tenant_ai = _tenant_ai_enabled_in_tx(db)
    db.commit()
    db.refresh(control)
    return _control_snapshot(control, tenant_ai_enabled=tenant_ai, cancelled_turns=cancelled)


def send_human_reply(
    db: Session,
    tenant: TenantContext,
    conversation_id: int,
    *,
    actor_user_id: str,
    body: str,
    idempotency_key: str,
    is_supervisor: bool = False,
    now: datetime | None = None,
) -> dict:
    """Queue a human outbound reply into the durable outbox (202) under single-owner & consent checks."""
    clean_body = body.strip()
    clean_key = idempotency_key.strip()
    if not clean_body:
        raise HTTPException(status_code=422, detail="Reply body must not be empty")
    if not clean_key or len(clean_key) > 120:
        raise HTTPException(status_code=422, detail="Idempotency key must be 1..120 characters")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_control_ready(db, tenant)
    conversation, control = _ensure_and_lock_control(db, conversation_id, current)
    if control.mode != "human_active":
        db.rollback()
        raise HTTPException(status_code=409, detail="Conversation must be claimed by a human operator before replying")
    if control.owner_user_id != actor_user_id and not is_supervisor:
        db.rollback()
        raise HTTPException(status_code=403, detail="Only the assigned operator or a supervisor can reply")

    channel = (conversation.message or {}).get("channel") or "whatsapp"
    if channel == "whatsapp":
        consent_ok = db.scalar(
            select(Cliente.consentimiento_datos).where(Cliente.whatsapp_id == conversation.session_id)
        )
        if consent_ok is not True:
            db.rollback()
            raise HTTPException(status_code=409, detail="Contact consent is not active for WhatsApp delivery")

    outbox_key = f"conv:{conversation_id}:{clean_key}"
    outbox_payload = {
        "conversation_id": conversation_id,
        "session_id": conversation.session_id,
        "channel": channel,
        "body": clean_body,
        "actor_user_id": actor_user_id,
    }
    job, duplicate = enqueue_outbox_action(
        db,
        tenant,
        action_type="conversation.human_reply.send",
        idempotency_key=outbox_key,
        payload=outbox_payload,
        available_at=current,
        commit=False,
    )
    external_id = f"human:{conversation_id}:{clean_key}"
    if duplicate:
        message = db.scalar(
            select(Message).where(
                Message.connection_id == "default",
                Message.channel == channel,
                Message.external_message_id == external_id,
            )
        )
        db.commit()
        return {
            "status": "queued",
            "duplicate": True,
            "outbox_job_id": job.id,
            "message_id": message.id if message else None,
            "conversation_id": conversation_id,
            "control_version": control.control_version,
        }

    message = Message(
        whatsapp_id=conversation.session_id,
        rol="agente",
        mensaje=clean_body,
        connection_id="default",
        channel=channel,
        external_message_id=external_id,
        direction="outbound",
        message_type="text",
        delivery_status="unknown",
        creado_en=current,
        recorded_at=current,
    )
    db.add(message)
    db.flush()
    db.commit()
    return {
        "status": "queued",
        "duplicate": False,
        "outbox_job_id": job.id,
        "message_id": message.id,
        "conversation_id": conversation_id,
        "control_version": control.control_version,
    }


def return_conversation_to_ai(
    db: Session,
    tenant: TenantContext,
    conversation_id: int,
    *,
    actor_user_id: str,
    expected_version: int,
    reason: str | None = None,
    is_supervisor: bool = False,
    now: datetime | None = None,
) -> dict:
    """Return control from human_active -> ai_active under a new monotonic control_version."""
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_control_ready(db, tenant)
    conversation, control = _ensure_and_lock_control(db, conversation_id, current)
    if control.control_version != expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale conversation control version")
    if control.mode != "human_active":
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Cannot return to AI from mode '{control.mode}'")
    if control.owner_user_id != actor_user_id and not is_supervisor:
        db.rollback()
        raise HTTPException(status_code=403, detail="Only the assigned operator or a supervisor can return control")

    tenant_ai = _tenant_ai_enabled_in_tx(db)
    if not tenant_ai or not control.ai_enabled:
        db.rollback()
        raise HTTPException(status_code=409, detail="AI is disabled by policy")

    channel = (conversation.message or {}).get("channel") or "whatsapp"
    if channel == "whatsapp":
        consent_ok = db.scalar(
            select(Cliente.consentimiento_datos).where(Cliente.whatsapp_id == conversation.session_id)
        )
        if consent_ok is not True:
            db.rollback()
            raise HTTPException(status_code=409, detail="Contact consent is required to return control to AI")

    from_mode = control.mode
    control.mode = "ai_active"
    control.owner_user_id = None
    control.control_version += 1
    control.updated_by = actor_user_id[:64]
    control.updated_at = current

    # Clear requires_human flag on latest lead so inbox reflects AI-active state.
    latest_lead = db.scalar(
        select(Lead)
        .join(Cliente, Lead.cliente_id == Cliente.id)
        .where(Cliente.whatsapp_id == conversation.session_id)
        .order_by(Lead.id.desc())
        .limit(1)
    )
    if latest_lead is not None and latest_lead.estado_seguimiento == "requiere_humano":
        latest_lead.estado_seguimiento = "activo"

    _record_transition(
        db,
        tenant,
        control,
        from_mode=from_mode,
        to_mode="ai_active",
        actor_user_id=actor_user_id,
        reason=reason.strip()[:180] if reason else None,
        event_type="conversation.control.changed",
        now=current,
    )
    db.commit()
    db.refresh(control)
    return _control_snapshot(control, tenant_ai_enabled=tenant_ai)


def resolve_conversation(
    db: Session,
    tenant: TenantContext,
    conversation_id: int,
    *,
    actor_user_id: str,
    expected_version: int,
    reason: str,
    is_supervisor: bool = False,
    now: datetime | None = None,
) -> dict:
    """Resolve a conversation with an explicit reason and cancel any recoverable AI turns."""
    clean_reason = reason.strip()[:180]
    if not clean_reason:
        raise HTTPException(status_code=422, detail="Resolution reason is required")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_control_ready(db, tenant)
    _, control = _ensure_and_lock_control(db, conversation_id, current)
    if control.control_version != expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale conversation control version")
    if control.mode == "resolved":
        db.rollback()
        raise HTTPException(status_code=409, detail="Conversation is already resolved")
    if control.mode == "human_active" and control.owner_user_id != actor_user_id and not is_supervisor:
        db.rollback()
        raise HTTPException(status_code=403, detail="Only the assigned operator or a supervisor can resolve")
    if control.mode in ("ai_active", "waiting_human") and not is_supervisor:
        db.rollback()
        raise HTTPException(status_code=409, detail="Claim the conversation before resolving")

    from_mode = control.mode
    control.mode = "resolved"
    control.owner_user_id = None
    control.resolution_reason = clean_reason
    control.control_version += 1
    control.updated_by = actor_user_id[:64]
    control.updated_at = current
    cancelled = _cancel_recoverable_ai_turns_in_tx(
        db, tenant, reason="control_resolved", now=current, conversation_id=conversation_id,
    )
    _record_transition(
        db,
        tenant,
        control,
        from_mode=from_mode,
        to_mode="resolved",
        actor_user_id=actor_user_id,
        reason=clean_reason,
        event_type="conversation.control.changed",
        now=current,
    )
    tenant_ai = _tenant_ai_enabled_in_tx(db)
    db.commit()
    db.refresh(control)
    return _control_snapshot(control, tenant_ai_enabled=tenant_ai, cancelled_turns=cancelled)
