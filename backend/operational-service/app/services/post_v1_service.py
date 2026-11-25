"""Reliable webhooks (FK-11), private attachments (FK-13), and conversational scheduling (FK-22)."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import json
import secrets
from typing import Sequence
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.services.action_outbox_service import enqueue_outbox_action
from app.services.tenant_data import bind_tenant_session
from app.tenant_models.operations import Cliente, Conversation
from app.tenant_models.opportunity import Opportunity
from app.tenant_models.post_v1 import (
    CalendarAppointment,
    PrivateAttachment,
    WebhookDelivery,
    WebhookSubscription,
)


ALLOWED_ATTACHMENT_TYPES = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "image/webp", "text/plain", "text/csv"}
)
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _require_table(db: Session, tenant: TenantContext, table_name: str) -> None:
    if not inspect(db.connection()).has_table(table_name, schema=tenant.schema_name):
        raise HTTPException(status_code=503, detail=f"Schema table '{table_name}' is unavailable")


# --- FK-11: Reliable webhooks with SSRF guard, HMAC signing, dedup, bounded attempts & diagnostics ---

def _validate_webhook_url(url: str) -> str:
    clean = url.strip()
    parsed = urlparse(clean)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(status_code=422, detail="Webhook target_url must use https:// with a valid host")
    host = parsed.hostname.lower()
    if host in ("localhost", "localhost.localdomain") or host.endswith(".local") or host.endswith(".internal"):
        raise HTTPException(status_code=422, detail="Webhook target_url cannot target local or internal hosts")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(status_code=422, detail="Webhook target_url cannot target private or loopback IPs")
    except ValueError:
        pass
    return clean


def sign_webhook_payload(secret: str, event_id: str, payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    mac = hmac.new(secret.encode("utf-8"), f"{event_id}.{body}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256={mac}"


def create_webhook_subscription(
    db: Session,
    tenant: TenantContext,
    *,
    name: str,
    target_url: str,
    event_types: Sequence[str],
    max_attempts: int = 5,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    clean_url = _validate_webhook_url(target_url)
    clean_name = name.strip()
    if not clean_name or len(clean_name) > 80:
        raise HTTPException(status_code=422, detail="Subscription name must be 1..80 characters")
    if not 1 <= max_attempts <= 10:
        raise HTTPException(status_code=422, detail="max_attempts must be between 1 and 10")
    cleaned_types = sorted({t.strip() for t in event_types if t and t.strip()})
    current = _now(now)
    secret = f"whsec_{secrets.token_urlsafe(32)}"

    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, WebhookSubscription.__tablename__)
    sub = WebhookSubscription(
        name=clean_name,
        target_url=clean_url,
        signing_secret=secret,
        event_types=cleaned_types,
        is_active=True,
        max_attempts=max_attempts,
        created_by=actor_user_id[:64] if actor_user_id else None,
        created_at=current,
        updated_at=current,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {
        "id": sub.id,
        "name": sub.name,
        "target_url": sub.target_url,
        "signing_secret": secret,
        "event_types": list(sub.event_types),
        "is_active": sub.is_active,
        "max_attempts": sub.max_attempts,
        "created_at": sub.created_at,
    }


def enqueue_webhook_delivery(
    db: Session,
    tenant: TenantContext,
    subscription_id: int,
    *,
    event_id: str,
    event_type: str,
    payload: dict,
    now: datetime | None = None,
) -> dict:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, WebhookDelivery.__tablename__)
    sub = db.get(WebhookSubscription, subscription_id)
    if sub is None or not sub.is_active:
        raise HTTPException(status_code=404, detail="Active webhook subscription not found")

    existing = db.scalar(
        select(WebhookDelivery).where(
            WebhookDelivery.subscription_id == subscription_id,
            WebhookDelivery.event_id == event_id,
        )
    )
    if existing is not None:
        return _webhook_delivery_to_dict(existing, duplicate=True)

    signature = sign_webhook_payload(sub.signing_secret, event_id, payload)
    job, _ = enqueue_outbox_action(
        db,
        tenant,
        action_type="webhook.deliver",
        idempotency_key=f"wh:{subscription_id}:{event_id}",
        payload={"subscription_id": subscription_id, "event_id": event_id, "event_type": event_type, "signature": signature},
        max_attempts=sub.max_attempts,
        available_at=current,
        commit=False,
    )
    delivery = WebhookDelivery(
        subscription_id=subscription_id,
        event_id=event_id[:64],
        event_type=event_type[:80],
        payload=dict(payload),
        signature=signature,
        status="queued",
        attempts=0,
        outbox_job_id=job.id,
        created_at=current,
        updated_at=current,
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return _webhook_delivery_to_dict(delivery, duplicate=False)


def record_webhook_attempt(
    db: Session,
    tenant: TenantContext,
    delivery_id: int,
    *,
    http_status: int | None,
    error: str | None = None,
    now: datetime | None = None,
) -> dict:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, WebhookDelivery.__tablename__)
    delivery = db.scalar(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id).with_for_update())
    if delivery is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Webhook delivery not found")
    sub = db.get(WebhookSubscription, delivery.subscription_id)
    max_attempts = sub.max_attempts if sub else 5

    delivery.attempts += 1
    delivery.last_http_status = http_status
    delivery.last_error = error.strip()[:160] if error else None
    if http_status is not None and 200 <= http_status < 300:
        delivery.status = "delivered"
        delivery.last_error = None
    elif delivery.attempts >= max_attempts:
        delivery.status = "dead_letter"
    else:
        delivery.status = "failed"
    delivery.updated_at = current
    db.commit()
    db.refresh(delivery)
    return _webhook_delivery_to_dict(delivery, duplicate=False)


def _webhook_delivery_to_dict(d: WebhookDelivery, *, duplicate: bool) -> dict:
    return {
        "id": d.id,
        "subscription_id": d.subscription_id,
        "event_id": d.event_id,
        "event_type": d.event_type,
        "signature": d.signature,
        "status": d.status,
        "attempts": d.attempts,
        "last_http_status": d.last_http_status,
        "last_error": d.last_error,
        "outbox_job_id": d.outbox_job_id,
        "duplicate": duplicate,
    }


# --- FK-13: Private attachments with size/type bounds, resource access & retention ---

def register_private_attachment(
    db: Session,
    tenant: TenantContext,
    *,
    resource_type: str,
    resource_id: int,
    filename: str,
    content_type: str,
    size_bytes: int,
    sha256_hex: str,
    uploaded_by: str,
    retention_days: int = 90,
    now: datetime | None = None,
) -> dict:
    if resource_type not in ("conversation", "contact", "opportunity"):
        raise HTTPException(status_code=422, detail="Unsupported attachment resource_type")
    norm_ct = content_type.strip().lower()
    if norm_ct not in ALLOWED_ATTACHMENT_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported content_type: {content_type}")
    if not 1 <= size_bytes <= MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=422, detail=f"Attachment size must be between 1 and {MAX_ATTACHMENT_BYTES} bytes")
    if len(sha256_hex.strip()) != 64:
        raise HTTPException(status_code=422, detail="sha256_hex must be a 64-character hex digest")
    if not 1 <= retention_days <= 3650:
        raise HTTPException(status_code=422, detail="retention_days must be between 1 and 3650")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, PrivateAttachment.__tablename__)
    model_map = {"conversation": Conversation, "contact": Cliente, "opportunity": Opportunity}
    if db.get(model_map[resource_type], resource_id) is None:
        raise HTTPException(status_code=404, detail=f"Target {resource_type} not found")

    safe_name = filename.replace("\\", "/").split("/")[-1].strip()[:180] or "attachment.bin"
    storage_key = f"{tenant.schema_name}/{resource_type}/{resource_id}/{uuid4().hex}"
    att = PrivateAttachment(
        resource_type=resource_type,
        resource_id=resource_id,
        filename=safe_name,
        content_type=norm_ct,
        size_bytes=size_bytes,
        sha256_hex=sha256_hex.strip().lower(),
        storage_key=storage_key,
        uploaded_by=uploaded_by[:64],
        expires_at=current + timedelta(days=retention_days),
        created_at=current,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return _attachment_to_dict(att)


def get_private_attachment(
    db: Session,
    tenant: TenantContext,
    attachment_id: int,
    *,
    resource_type: str,
    resource_id: int,
    now: datetime | None = None,
) -> dict:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, PrivateAttachment.__tablename__)
    att = db.get(PrivateAttachment, attachment_id)
    if (
        att is None
        or att.deleted_at is not None
        or att.expires_at <= current
        or att.resource_type != resource_type
        or att.resource_id != resource_id
    ):
        raise HTTPException(status_code=404, detail="Attachment not found")
    return _attachment_to_dict(att)


def purge_expired_attachments(db: Session, tenant: TenantContext, *, now: datetime | None = None) -> int:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, PrivateAttachment.__tablename__)
    res = db.execute(delete(PrivateAttachment).where(PrivateAttachment.expires_at <= current))
    db.commit()
    return int(res.rowcount or 0)


def _attachment_to_dict(att: PrivateAttachment) -> dict:
    return {
        "id": att.id,
        "resource_type": att.resource_type,
        "resource_id": att.resource_id,
        "filename": att.filename,
        "content_type": att.content_type,
        "size_bytes": att.size_bytes,
        "sha256_hex": att.sha256_hex,
        "storage_key": att.storage_key,
        "uploaded_by": att.uploaded_by,
        "expires_at": att.expires_at,
        "created_at": att.created_at,
    }


# --- FK-22: Conversational scheduling (simulate + double-book-safe confirm) ---

def _lock_calendar_resource(db: Session, schema_name: str, resource_key: str) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"flowkron-cal:{schema_name}:{resource_key}"},
    )


def simulate_appointment_slot(
    db: Session,
    tenant: TenantContext,
    *,
    resource_key: str,
    starts_at: datetime,
    ends_at: datetime,
) -> dict:
    start_utc = _now(starts_at)
    end_utc = _now(ends_at)
    if end_utc <= start_utc:
        raise HTTPException(status_code=422, detail="ends_at must be strictly after starts_at")
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, CalendarAppointment.__tablename__)

    conflicts = list(
        db.scalars(
            select(CalendarAppointment).where(
                CalendarAppointment.resource_key == resource_key.strip()[:64],
                CalendarAppointment.status == "confirmed",
                CalendarAppointment.starts_at < end_utc,
                CalendarAppointment.ends_at > start_utc,
            )
        ).all()
    )
    return {
        "available": len(conflicts) == 0,
        "conflict_ids": [c.id for c in conflicts],
    }


def confirm_appointment(
    db: Session,
    tenant: TenantContext,
    *,
    resource_key: str,
    client_id: int,
    title: str,
    starts_at: datetime,
    ends_at: datetime,
    idempotency_key: str,
    conversation_id: int | None = None,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    start_utc = _now(starts_at)
    end_utc = _now(ends_at)
    if end_utc <= start_utc:
        raise HTTPException(status_code=422, detail="ends_at must be strictly after starts_at")
    clean_resource = resource_key.strip()[:64]
    clean_key = idempotency_key.strip()[:180]
    if not clean_resource or not clean_key:
        raise HTTPException(status_code=422, detail="resource_key and idempotency_key are required")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, CalendarAppointment.__tablename__)
    _lock_calendar_resource(db, tenant.schema_name, clean_resource)

    existing = db.scalar(select(CalendarAppointment).where(CalendarAppointment.idempotency_key == clean_key))
    if existing is not None:
        db.commit()
        return _appointment_to_dict(existing, duplicate=True)

    if db.get(Cliente, client_id) is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Contact not found")

    overlap = db.scalar(
        select(CalendarAppointment.id).where(
            CalendarAppointment.resource_key == clean_resource,
            CalendarAppointment.status == "confirmed",
            CalendarAppointment.starts_at < end_utc,
            CalendarAppointment.ends_at > start_utc,
        ).limit(1)
    )
    if overlap is not None:
        db.rollback()
        raise HTTPException(status_code=409, detail="Requested appointment slot conflicts with an existing booking")

    appt = CalendarAppointment(
        resource_key=clean_resource,
        client_id=client_id,
        conversation_id=conversation_id,
        title=title.strip()[:160],
        starts_at=start_utc,
        ends_at=end_utc,
        status="confirmed",
        idempotency_key=clean_key,
        created_by=actor_user_id[:64] if actor_user_id else None,
        created_at=current,
        updated_at=current,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return _appointment_to_dict(appt, duplicate=False)


def cancel_appointment(
    db: Session,
    tenant: TenantContext,
    appointment_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, CalendarAppointment.__tablename__)
    appt = db.scalar(select(CalendarAppointment).where(CalendarAppointment.id == appointment_id).with_for_update())
    if appt is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Appointment not found")
    appt.status = "cancelled"
    appt.updated_at = current
    db.commit()
    db.refresh(appt)
    return _appointment_to_dict(appt, duplicate=False)


def _appointment_to_dict(a: CalendarAppointment, *, duplicate: bool) -> dict:
    return {
        "id": a.id,
        "resource_key": a.resource_key,
        "client_id": a.client_id,
        "conversation_id": a.conversation_id,
        "title": a.title,
        "starts_at": a.starts_at,
        "ends_at": a.ends_at,
        "status": a.status,
        "idempotency_key": a.idempotency_key,
        "duplicate": duplicate,
    }
