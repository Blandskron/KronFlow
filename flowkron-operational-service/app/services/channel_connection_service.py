"""Delegated tenant channel connections (FK-24) and conversation-linked email (FK-23)."""

from datetime import datetime, timezone
import hashlib

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.services.action_outbox_service import enqueue_outbox_action
from app.services.contact_points import normalize_email
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.campaigns import TenantChannelConnection
from app.tenant_models.operations import Conversation, Message


VALID_CHANNEL_PROVIDERS = {
    "email": frozenset({"stub", "resend"}),
    "whatsapp": frozenset({"stub", "whatsapp_business_official"}),
}


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Connection timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _fingerprint(secret: str | None) -> str | None:
    if not secret or not secret.strip():
        return None
    return hashlib.sha256(secret.strip().encode("utf-8")).hexdigest()[:32]


def connections_ready(db: Session, tenant: TenantContext) -> bool:
    return inspect(db.connection()).has_table(TenantChannelConnection.__tablename__, schema=tenant.schema_name)


def _require_ready(db: Session, tenant: TenantContext) -> None:
    if not connections_ready(db, tenant):
        raise HTTPException(status_code=503, detail="Channel connection schema is unavailable")


def _conn_to_dict(conn: TenantChannelConnection) -> dict:
    return {
        "id": conn.id,
        "channel": conn.channel,
        "provider": conn.provider,
        "sender_address": conn.sender_address,
        "display_name": conn.display_name,
        "status": conn.status,
        "verified": conn.verified,
        "sandbox_only": conn.sandbox_only,
        "credential_version": conn.credential_version,
        "revoked_at": conn.revoked_at,
        "created_by": conn.created_by,
        "created_at": conn.created_at,
        "updated_at": conn.updated_at,
    }


def create_channel_connection(
    db: Session,
    tenant: TenantContext,
    *,
    channel: str,
    provider: str,
    sender_address: str,
    display_name: str,
    verified: bool = False,
    sandbox_only: bool = True,
    provider_secret: str | None = None,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    norm_channel = channel.strip().lower()
    norm_provider = provider.strip().lower()
    if norm_channel not in VALID_CHANNEL_PROVIDERS or norm_provider not in VALID_CHANNEL_PROVIDERS[norm_channel]:
        raise HTTPException(status_code=422, detail=f"Unsupported provider '{provider}' for channel '{channel}'")

    if norm_channel == "email":
        norm_sender = normalize_email(sender_address)
        if norm_sender is None:
            raise HTTPException(status_code=422, detail="Invalid sender email address")
    else:
        norm_sender = sender_address.strip()
        if not norm_sender or len(norm_sender) > 255:
            raise HTTPException(status_code=422, detail="Invalid sender address")

    clean_name = display_name.strip()
    if not clean_name or len(clean_name) > 120:
        raise HTTPException(status_code=422, detail="display_name must be 1..120 characters")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    conn = TenantChannelConnection(
        channel=norm_channel,
        provider=norm_provider,
        sender_address=norm_sender,
        display_name=clean_name,
        status="active" if (verified or norm_provider == "stub") else "pending_verification",
        verified=bool(verified or norm_provider == "stub"),
        sandbox_only=bool(sandbox_only),
        secret_fingerprint=_fingerprint(provider_secret),
        credential_version=1,
        created_by=actor_user_id[:64] if actor_user_id else None,
        created_at=current,
        updated_at=current,
    )
    db.add(conn)
    db.flush()
    create_system_event(
        db,
        "channel.connection.created",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"connection_id": conn.id, "channel": norm_channel, "provider": norm_provider, "sandbox_only": conn.sandbox_only},
    )
    db.commit()
    db.refresh(conn)
    return _conn_to_dict(conn)


def list_channel_connections(db: Session, tenant: TenantContext, *, channel: str | None = None) -> list[dict]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    stmt = select(TenantChannelConnection)
    if channel:
        stmt = stmt.where(TenantChannelConnection.channel == channel.strip().lower())
    rows = db.scalars(stmt.order_by(TenantChannelConnection.id.desc())).all()
    return [_conn_to_dict(row) for row in rows]


def rotate_channel_connection(
    db: Session,
    tenant: TenantContext,
    connection_id: int,
    *,
    new_provider_secret: str,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    fp = _fingerprint(new_provider_secret)
    if fp is None:
        raise HTTPException(status_code=422, detail="new_provider_secret must not be empty")
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    conn = db.scalar(
        select(TenantChannelConnection).where(TenantChannelConnection.id == connection_id).with_for_update()
    )
    if conn is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Channel connection not found")
    if conn.status == "revoked":
        db.rollback()
        raise HTTPException(status_code=409, detail="Cannot rotate a revoked connection")
    conn.secret_fingerprint = fp
    conn.credential_version += 1
    conn.updated_at = current
    create_system_event(
        db,
        "channel.connection.rotated",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"connection_id": conn.id, "credential_version": conn.credential_version, "actor_user_id": actor_user_id},
    )
    db.commit()
    db.refresh(conn)
    return _conn_to_dict(conn)


def revoke_channel_connection(
    db: Session,
    tenant: TenantContext,
    connection_id: int,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    conn = db.scalar(
        select(TenantChannelConnection).where(TenantChannelConnection.id == connection_id).with_for_update()
    )
    if conn is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Channel connection not found")
    if conn.status != "revoked":
        conn.status = "revoked"
        conn.revoked_at = current
        conn.updated_at = current
        create_system_event(
            db,
            "channel.connection.revoked",
            tenant.auth_tenant_id,
            tenant.schema_name,
            {"connection_id": conn.id, "actor_user_id": actor_user_id},
        )
        db.commit()
        db.refresh(conn)
    else:
        db.commit()
    return _conn_to_dict(conn)


def send_conversation_email(
    db: Session,
    tenant: TenantContext,
    conversation_id: int,
    *,
    connection_id: int,
    to_email: str,
    subject: str,
    body_text: str,
    idempotency_key: str,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict:
    """Queue a conversation-linked outbound email (FK-23) using a verified delegated email connection."""
    norm_to = normalize_email(to_email)
    if norm_to is None:
        raise HTTPException(status_code=422, detail="Invalid recipient email address")
    clean_subject = subject.strip()
    clean_body = body_text.strip()
    clean_key = idempotency_key.strip()
    if not clean_subject or len(clean_subject) > 200:
        raise HTTPException(status_code=422, detail="subject must be 1..200 characters")
    if not clean_body:
        raise HTTPException(status_code=422, detail="body_text must not be empty")
    if not clean_key or len(clean_key) > 120:
        raise HTTPException(status_code=422, detail="idempotency_key must be 1..120 characters")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conn = db.get(TenantChannelConnection, connection_id)
    if conn is None or conn.channel != "email":
        raise HTTPException(status_code=404, detail="Email channel connection not found")
    if conn.status != "active" or not conn.verified:
        raise HTTPException(status_code=409, detail="Email channel connection is not active and verified")

    outbox_key = f"conv-email:{conversation_id}:{clean_key}"
    payload = {
        "conversation_id": conversation_id,
        "connection_id": conn.id,
        "provider": conn.provider,
        "from": conn.sender_address,
        "to": norm_to,
        "subject": clean_subject,
        "body_text": clean_body,
        "actor_user_id": actor_user_id,
    }
    job, duplicate = enqueue_outbox_action(
        db,
        tenant,
        action_type="conversation.email.send",
        idempotency_key=outbox_key,
        payload=payload,
        available_at=current,
        commit=False,
    )
    external_id = f"conv-email:{conversation_id}:{clean_key}"
    if duplicate:
        existing_msg = db.scalar(
            select(Message).where(
                Message.connection_id == f"email:{conn.id}",
                Message.channel == "email",
                Message.external_message_id == external_id,
            )
        )
        db.commit()
        return {
            "status": "queued",
            "duplicate": True,
            "outbox_job_id": job.id,
            "message_id": existing_msg.id if existing_msg else None,
            "conversation_id": conversation_id,
            "connection_id": conn.id,
        }

    msg = Message(
        whatsapp_id=conversation.session_id,
        rol="agente",
        mensaje=f"[{clean_subject}] {clean_body}",
        connection_id=f"email:{conn.id}",
        channel="email",
        external_message_id=external_id,
        direction="outbound",
        message_type="email",
        delivery_status="unknown",
        creado_en=current,
        recorded_at=current,
    )
    db.add(msg)
    db.flush()
    create_system_event(
        db,
        "conversation.email.queued",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"conversation_id": conversation_id, "connection_id": conn.id, "outbox_job_id": job.id, "message_id": msg.id},
    )
    db.commit()
    return {
        "status": "queued",
        "duplicate": False,
        "outbox_job_id": job.id,
        "message_id": msg.id,
        "conversation_id": conversation_id,
        "connection_id": conn.id,
    }
