"""Scoped memory (FK-20), confirmed enrichment (FK-21), external notifications (FK-25), and AI cost ledger (FK-26)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.contracts import audit_correlation
from app.core.tenant_resolver import TenantContext
from app.services.action_outbox_service import enqueue_outbox_action
from app.services.contact_points import normalize_email, normalize_phone
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.ai_extensions import (
    AIUsageRecord,
    ContactEnrichmentCandidate,
    ConversationMemoryItem,
    ExternalNotificationDelivery,
)
from app.tenant_models.operations import Cliente, Conversation


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _require_table(db: Session, tenant: TenantContext, table_name: str) -> None:
    if not inspect(db.connection()).has_table(table_name, schema=tenant.schema_name):
        raise HTTPException(status_code=503, detail=f"Schema table '{table_name}' is unavailable")


# --- FK-20: Scoped conversation memory with source and retention ---

def record_conversation_memory(
    db: Session,
    tenant: TenantContext,
    conversation_id: int,
    *,
    memory_key: str,
    memory_value: str,
    source_type: str,
    source_ref: str,
    ttl_days: int = 30,
    now: datetime | None = None,
) -> dict:
    if source_type not in ("message", "operator", "document", "system"):
        raise HTTPException(status_code=422, detail="Invalid memory source_type")
    if not 1 <= ttl_days <= 365:
        raise HTTPException(status_code=422, detail="ttl_days must be between 1 and 365")
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, ConversationMemoryItem.__tablename__)
    if db.get(Conversation, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    item = ConversationMemoryItem(
        conversation_id=conversation_id,
        memory_key=memory_key.strip()[:64],
        memory_value=memory_value.strip(),
        source_type=source_type,
        source_ref=source_ref.strip()[:120],
        expires_at=current + timedelta(days=ttl_days),
        created_at=current,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "id": item.id,
        "conversation_id": item.conversation_id,
        "memory_key": item.memory_key,
        "memory_value": item.memory_value,
        "source_type": item.source_type,
        "source_ref": item.source_ref,
        "expires_at": item.expires_at,
        "created_at": item.created_at,
    }


def list_conversation_memory(
    db: Session,
    tenant: TenantContext,
    conversation_id: int,
    *,
    limit: int = 20,
    now: datetime | None = None,
) -> list[dict]:
    """Return only active (non-expired) memory items scoped strictly to this conversation."""
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, ConversationMemoryItem.__tablename__)
    rows = db.scalars(
        select(ConversationMemoryItem)
        .where(
            ConversationMemoryItem.conversation_id == conversation_id,
            ConversationMemoryItem.expires_at > current,
        )
        .order_by(ConversationMemoryItem.id.desc())
        .limit(max(1, min(limit, 50)))
    ).all()
    return [
        {
            "id": r.id,
            "conversation_id": r.conversation_id,
            "memory_key": r.memory_key,
            "memory_value": r.memory_value,
            "source_type": r.source_type,
            "source_ref": r.source_ref,
            "expires_at": r.expires_at,
            "created_at": r.created_at,
        }
        for r in rows
    ]


def purge_expired_memory(db: Session, tenant: TenantContext, *, now: datetime | None = None) -> int:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, ConversationMemoryItem.__tablename__)
    res = db.execute(delete(ConversationMemoryItem).where(ConversationMemoryItem.expires_at <= current))
    db.commit()
    return int(res.rowcount or 0)


# --- FK-21: Confirmed CRM enrichment with source and conflict control ---

def propose_contact_enrichment(
    db: Session,
    tenant: TenantContext,
    client_id: int,
    *,
    field_name: str,
    proposed_value: str,
    source: str,
    now: datetime | None = None,
) -> dict:
    if field_name not in ("nombre", "email", "telefono"):
        raise HTTPException(status_code=422, detail="field_name must be nombre, email, or telefono")
    clean_val = proposed_value.strip()
    if field_name == "email":
        norm = normalize_email(clean_val)
        if norm is None:
            raise HTTPException(status_code=422, detail="Invalid email format")
        clean_val = norm
    elif field_name == "telefono":
        norm = normalize_phone(clean_val)
        if norm is None:
            raise HTTPException(status_code=422, detail="Phone requires international + prefix")
        clean_val = norm
    elif not clean_val or len(clean_val) > 160:
        raise HTTPException(status_code=422, detail="Invalid nombre")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, ContactEnrichmentCandidate.__tablename__)
    client = db.get(Cliente, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    prev = getattr(client, field_name)
    candidate = ContactEnrichmentCandidate(
        client_id=client_id,
        field_name=field_name,
        proposed_value=clean_val,
        previous_value=prev,
        source=source.strip()[:64] or "agent-core",
        status="pending",
        created_at=current,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return _enrichment_to_dict(candidate)


def _enrichment_to_dict(c: ContactEnrichmentCandidate) -> dict:
    return {
        "id": c.id,
        "client_id": c.client_id,
        "field_name": c.field_name,
        "proposed_value": c.proposed_value,
        "previous_value": c.previous_value,
        "source": c.source,
        "status": c.status,
        "reviewed_by": c.reviewed_by,
        "reviewed_at": c.reviewed_at,
        "created_at": c.created_at,
    }


def apply_contact_enrichment(
    db: Session,
    tenant: TenantContext,
    candidate_id: int,
    *,
    reviewer_user_id: str,
    allow_overwrite: bool = False,
    now: datetime | None = None,
) -> dict:
    """Apply confirmed enrichment only if no conflict exists (unless explicitly overridden)."""
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, ContactEnrichmentCandidate.__tablename__)
    cand = db.scalar(
        select(ContactEnrichmentCandidate).where(ContactEnrichmentCandidate.id == candidate_id).with_for_update()
    )
    if cand is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Enrichment candidate not found")
    if cand.status != "pending":
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Enrichment candidate is already '{cand.status}'")

    client = db.scalar(select(Cliente).where(Cliente.id == cand.client_id).with_for_update())
    if client is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Contact not found")

    current_value = getattr(client, cand.field_name)
    if current_value and current_value != cand.proposed_value and not allow_overwrite:
        cand.status = "conflict"
        cand.previous_value = current_value
        cand.reviewed_by = reviewer_user_id[:64]
        cand.reviewed_at = current
        db.commit()
        raise HTTPException(status_code=409, detail="Contact field already has a conflicting value")

    setattr(client, cand.field_name, cand.proposed_value)
    cand.status = "applied"
    cand.reviewed_by = reviewer_user_id[:64]
    cand.reviewed_at = current
    create_system_event(
        db,
        "crm.contact.enriched",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"candidate_id": cand.id, "client_id": client.id, "field_name": cand.field_name, "source": cand.source},
    )
    db.commit()
    db.refresh(cand)
    return _enrichment_to_dict(cand)


# --- FK-25: External notification delivery with deduplication and receipts ---

def enqueue_external_notification(
    db: Session,
    tenant: TenantContext,
    *,
    dedup_key: str,
    event_type: str,
    channel: str,
    recipient: str,
    payload: dict,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict:
    if channel not in ("email", "webhook_stub"):
        raise HTTPException(status_code=422, detail="Unsupported notification channel")
    clean_key = dedup_key.strip()[:180]
    if not clean_key:
        raise HTTPException(status_code=422, detail="dedup_key is required")
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, ExternalNotificationDelivery.__tablename__)

    existing = db.scalar(
        select(ExternalNotificationDelivery).where(ExternalNotificationDelivery.dedup_key == clean_key)
    )
    if existing is not None:
        return {
            "id": existing.id,
            "dedup_key": existing.dedup_key,
            "status": existing.status,
            "outbox_job_id": existing.outbox_job_id,
            "receipt_ref": existing.receipt_ref,
            "duplicate": True,
        }

    job, _ = enqueue_outbox_action(
        db,
        tenant,
        action_type="notification.external.send",
        idempotency_key=f"notif:{clean_key}",
        payload={"event_type": event_type, "channel": channel, "recipient": recipient, "payload": payload},
        available_at=current,
        commit=False,
    )
    delivery = ExternalNotificationDelivery(
        dedup_key=clean_key,
        event_type=event_type.strip()[:64],
        channel=channel,
        recipient=recipient.strip()[:255],
        payload=dict(payload),
        status="queued",
        outbox_job_id=job.id,
        created_by=actor_user_id[:64],
        created_at=current,
        updated_at=current,
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return {
        "id": delivery.id,
        "dedup_key": delivery.dedup_key,
        "status": delivery.status,
        "outbox_job_id": delivery.outbox_job_id,
        "receipt_ref": delivery.receipt_ref,
        "duplicate": False,
    }


def record_notification_receipt(
    db: Session,
    tenant: TenantContext,
    delivery_id: int,
    *,
    status_value: str,
    receipt_ref: str | None = None,
    now: datetime | None = None,
) -> dict:
    if status_value not in ("delivered", "failed"):
        raise HTTPException(status_code=422, detail="status must be 'delivered' or 'failed'")
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, ExternalNotificationDelivery.__tablename__)
    delivery = db.scalar(
        select(ExternalNotificationDelivery).where(ExternalNotificationDelivery.id == delivery_id).with_for_update()
    )
    if delivery is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Notification delivery not found")
    delivery.status = status_value
    delivery.receipt_ref = receipt_ref.strip()[:180] if receipt_ref else delivery.receipt_ref
    delivery.updated_at = current
    db.commit()
    db.refresh(delivery)
    return {
        "id": delivery.id,
        "dedup_key": delivery.dedup_key,
        "status": delivery.status,
        "outbox_job_id": delivery.outbox_job_id,
        "receipt_ref": delivery.receipt_ref,
        "duplicate": False,
    }


# --- FK-26: Tenant AI usage & accumulated cost ledger ---

def record_ai_usage(
    db: Session,
    tenant: TenantContext,
    *,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    estimated_cost_usd: Decimal,
    is_simulation: bool = False,
    agent_id: int | None = None,
    agent_revision_id: int | None = None,
    pricing_version: str | None = None,
    correlation_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    if prompt_tokens < 0 or completion_tokens < 0 or latency_ms < 0 or estimated_cost_usd < 0:
        raise HTTPException(status_code=422, detail="AI usage metrics must be non-negative")
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, AIUsageRecord.__tablename__)

    row = AIUsageRecord(
        provider=provider.strip()[:48],
        model=model.strip()[:80],
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        estimated_cost_usd=estimated_cost_usd,
        is_simulation=bool(is_simulation),
        agent_id=agent_id,
        agent_revision_id=agent_revision_id,
        pricing_version=pricing_version.strip()[:32] if pricing_version else None,
        correlation_id=correlation_id or audit_correlation.get(),
        recorded_at=current,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "provider": row.provider,
        "model": row.model,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "latency_ms": row.latency_ms,
        "estimated_cost_usd": str(row.estimated_cost_usd),
        "is_simulation": row.is_simulation,
        "agent_id": row.agent_id,
        "agent_revision_id": row.agent_revision_id,
        "pricing_version": row.pricing_version,
        "correlation_id": row.correlation_id,
        "recorded_at": row.recorded_at,
    }


def summarize_ai_usage(
    db: Session,
    tenant: TenantContext,
    *,
    days: int = 30,
    include_simulations: bool = False,
    now: datetime | None = None,
) -> dict:
    current = _now(now)
    cutoff = current - timedelta(days=max(1, min(days, 365)))
    bind_tenant_session(db, tenant.schema_name)
    _require_table(db, tenant, AIUsageRecord.__tablename__)

    stmt = select(
        func.count().label("requests"),
        func.coalesce(func.sum(AIUsageRecord.prompt_tokens), 0).label("prompt_tokens"),
        func.coalesce(func.sum(AIUsageRecord.completion_tokens), 0).label("completion_tokens"),
        func.coalesce(func.sum(AIUsageRecord.estimated_cost_usd), Decimal("0")).label("total_cost_usd"),
        func.coalesce(func.avg(AIUsageRecord.latency_ms), 0).label("avg_latency_ms"),
    ).where(AIUsageRecord.recorded_at >= cutoff)
    if not include_simulations:
        stmt = stmt.where(AIUsageRecord.is_simulation.is_(False))
    row = db.execute(stmt).mappings().one()
    return {
        "days": days,
        "requests": int(row["requests"]),
        "prompt_tokens": int(row["prompt_tokens"]),
        "completion_tokens": int(row["completion_tokens"]),
        "total_cost_usd": str(row["total_cost_usd"]),
        "avg_latency_ms": round(float(row["avg_latency_ms"]), 2),
    }
