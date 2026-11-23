"""Transactional action outbox with idempotent enqueue, bounded leases, and effect verification (FK-03)."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from typing import Sequence

from fastapi import HTTPException
from sqlalchemy import inspect, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.contracts import audit_correlation
from app.core.tenant_resolver import TenantContext
from app.services.tenant_data import bind_tenant_session
from app.tenant_models.action_outbox import ActionOutboxJob


DEFAULT_LEASE_SECONDS = 120
DEFAULT_MAX_ATTEMPTS = 5
MAX_CLAIM_BATCH = 50


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Outbox timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def canonical_payload_hash(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def outbox_ready(db: Session, tenant: TenantContext) -> bool:
    return inspect(db.connection()).has_table(ActionOutboxJob.__tablename__, schema=tenant.schema_name)


def _require_outbox_ready(db: Session, tenant: TenantContext) -> None:
    if not outbox_ready(db, tenant):
        raise HTTPException(status_code=503, detail="Action outbox schema is unavailable")


def _load_locked_job(db: Session, tenant: TenantContext, job_id: int) -> ActionOutboxJob:
    bind_tenant_session(db, tenant.schema_name)
    _require_outbox_ready(db, tenant)
    job = db.scalar(select(ActionOutboxJob).where(ActionOutboxJob.id == job_id).with_for_update())
    if job is None:
        raise HTTPException(status_code=404, detail="Outbox job not found")
    return job


def _verify_claim(job: ActionOutboxJob, claim_token: str, now: datetime, *, allow_expired: bool = False) -> None:
    if not job.claim_token or not hmac.compare_digest(job.claim_token, claim_token):
        raise HTTPException(status_code=409, detail="Stale outbox claim")
    if not allow_expired and (job.lease_until is None or job.lease_until <= now):
        raise HTTPException(status_code=409, detail="Outbox claim expired")


def enqueue_outbox_action(
    db: Session,
    tenant: TenantContext,
    *,
    action_type: str,
    idempotency_key: str,
    payload: dict,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    available_at: datetime | None = None,
    correlation_id: str | None = None,
    commit: bool = False,
) -> tuple[ActionOutboxJob, bool]:
    """Insert an outbox action in the caller's transaction. Returns (job, duplicate)."""
    action_type = action_type.strip()
    idempotency_key = idempotency_key.strip()
    if not action_type or len(action_type) > 64:
        raise ValueError("action_type must be a non-empty string up to 64 characters")
    if not idempotency_key or len(idempotency_key) > 180:
        raise ValueError("idempotency_key must be a non-empty string up to 180 characters")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    bind_tenant_session(db, tenant.schema_name)
    _require_outbox_ready(db, tenant)

    now = _utc_now()
    ready_at = _utc_now(available_at) if available_at is not None else now
    digest = canonical_payload_hash(payload)
    resolved_correlation = correlation_id or audit_correlation.get()

    inserted_id = db.scalar(
        insert(ActionOutboxJob)
        .values(
            action_type=action_type,
            idempotency_key=idempotency_key,
            payload_hash=digest,
            payload=payload,
            state="pending",
            attempts=0,
            max_attempts=max_attempts,
            available_at=ready_at,
            correlation_id=resolved_correlation,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["action_type", "idempotency_key"])
        .returning(ActionOutboxJob.id)
    )
    if inserted_id is not None:
        job = db.get(ActionOutboxJob, inserted_id)
        if commit:
            db.commit()
            db.refresh(job)
        return job, False

    existing = db.scalar(
        select(ActionOutboxJob).where(
            ActionOutboxJob.action_type == action_type,
            ActionOutboxJob.idempotency_key == idempotency_key,
        )
    )
    if existing is None:
        raise HTTPException(status_code=409, detail="Outbox idempotency conflict")
    if existing.payload_hash != digest:
        raise HTTPException(status_code=409, detail="Idempotency key reused with a different payload")
    if commit:
        db.commit()
    return existing, True


def claim_next_outbox_jobs(
    db: Session,
    tenant: TenantContext,
    *,
    action_types: Sequence[str] | None = None,
    limit: int = 1,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> list[ActionOutboxJob]:
    """Reclaim expired leases safely and claim up to `limit` runnable jobs with SKIP LOCKED."""
    if limit < 1 or limit > MAX_CLAIM_BATCH:
        raise ValueError(f"limit must be between 1 and {MAX_CLAIM_BATCH}")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")

    bind_tenant_session(db, tenant.schema_name)
    _require_outbox_ready(db, tenant)
    current = _utc_now(now)

    # First reconcile expired leases: executing -> unknown (never blind-retry),
    # claimed with exhausted attempts -> failed.
    reconcile_query = select(ActionOutboxJob).where(
        ActionOutboxJob.lease_until.is_not(None),
        ActionOutboxJob.lease_until <= current,
        ActionOutboxJob.state.in_(("executing", "claimed")),
    )
    if action_types:
        reconcile_query = reconcile_query.where(ActionOutboxJob.action_type.in_(tuple(action_types)))
    expired_jobs = list(
        db.scalars(reconcile_query.order_by(ActionOutboxJob.id).with_for_update(skip_locked=True)).all()
    )
    for job in expired_jobs:
        if job.state == "executing":
            job.state = "unknown"
            job.last_error = "execution_outcome_unknown"
            job.claim_token = None
            job.lease_until = None
            job.updated_at = current
        elif job.state == "claimed" and job.attempts >= job.max_attempts:
            job.state = "failed"
            job.last_error = "attempt_limit_reached"
            job.claim_token = None
            job.lease_until = None
            job.updated_at = current

    claim_query = select(ActionOutboxJob).where(
        ActionOutboxJob.available_at <= current,
        ActionOutboxJob.attempts < ActionOutboxJob.max_attempts,
        or_(
            ActionOutboxJob.state == "pending",
            (ActionOutboxJob.state == "claimed") & (ActionOutboxJob.lease_until <= current),
        ),
    )
    if action_types:
        claim_query = claim_query.where(ActionOutboxJob.action_type.in_(tuple(action_types)))

    claimed = list(
        db.scalars(
            claim_query.order_by(ActionOutboxJob.available_at, ActionOutboxJob.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
    )
    for job in claimed:
        job.state = "claimed"
        job.attempts += 1
        job.claim_token = secrets.token_urlsafe(32)
        job.lease_until = current + timedelta(seconds=lease_seconds)
        job.last_error = None
        job.updated_at = current

    db.commit()
    for job in claimed:
        db.refresh(job)
    return claimed


def begin_outbox_execution(
    db: Session,
    tenant: TenantContext,
    job_id: int,
    claim_token: str,
    *,
    now: datetime | None = None,
) -> ActionOutboxJob:
    """Durable barrier before triggering an external side effect."""
    current = _utc_now(now)
    job = _load_locked_job(db, tenant, job_id)
    _verify_claim(job, claim_token, current)
    if job.state != "claimed":
        raise HTTPException(status_code=409, detail=f"Cannot begin execution from state '{job.state}'")
    job.state = "executing"
    job.updated_at = current
    db.commit()
    db.refresh(job)
    return job


def complete_outbox_action(
    db: Session,
    tenant: TenantContext,
    job_id: int,
    claim_token: str,
    *,
    effect_reference: str | None = None,
    effect_payload: dict | None = None,
    now: datetime | None = None,
) -> ActionOutboxJob:
    """Record verified completion for a claimed or executing job."""
    current = _utc_now(now)
    job = _load_locked_job(db, tenant, job_id)
    if job.state == "completed":
        if effect_reference is None or job.effect_reference == effect_reference:
            db.commit()
            return job
        db.rollback()
        raise HTTPException(status_code=409, detail="Outbox job already completed with another effect reference")
    _verify_claim(job, claim_token, current, allow_expired=(job.state == "executing"))
    if job.state not in ("claimed", "executing"):
        raise HTTPException(status_code=409, detail=f"Cannot complete outbox job from state '{job.state}'")
    job.state = "completed"
    job.effect_reference = effect_reference
    job.effect_payload = effect_payload
    job.claim_token = None
    job.lease_until = None
    job.last_error = None
    job.completed_at = current
    job.updated_at = current
    db.commit()
    db.refresh(job)
    return job


def fail_outbox_action(
    db: Session,
    tenant: TenantContext,
    job_id: int,
    claim_token: str,
    *,
    error: str,
    retryable: bool,
    retry_delay_seconds: int = 30,
    now: datetime | None = None,
) -> ActionOutboxJob:
    """Handle failure without blind-retrying jobs whose external effect may have started."""
    current = _utc_now(now)
    job = _load_locked_job(db, tenant, job_id)
    _verify_claim(job, claim_token, current, allow_expired=(job.state == "executing"))
    if job.state not in ("claimed", "executing"):
        raise HTTPException(status_code=409, detail=f"Cannot fail outbox job from state '{job.state}'")

    error_text = error.strip()[:120] or "action_failed"
    if retryable and job.state == "executing":
        # External call may have succeeded before the error/timeout; require verification.
        job.state = "unknown"
        job.last_error = error_text
    elif retryable and job.state == "claimed" and job.attempts < job.max_attempts:
        job.state = "pending"
        job.available_at = current + timedelta(seconds=max(0, retry_delay_seconds))
        job.last_error = error_text
    else:
        job.state = "failed"
        job.last_error = error_text

    job.claim_token = None
    job.lease_until = None
    job.updated_at = current
    db.commit()
    db.refresh(job)
    return job


def reconcile_unknown_outbox_action(
    db: Session,
    tenant: TenantContext,
    job_id: int,
    *,
    verified_applied: bool,
    effect_reference: str | None = None,
    effect_payload: dict | None = None,
    retry_delay_seconds: int = 0,
    now: datetime | None = None,
) -> ActionOutboxJob:
    """Resolve an `unknown` job after verifying whether the external effect was applied."""
    current = _utc_now(now)
    job = _load_locked_job(db, tenant, job_id)
    if job.state != "unknown":
        raise HTTPException(status_code=409, detail=f"Only unknown jobs can be reconciled, got '{job.state}'")

    if verified_applied:
        job.state = "completed"
        job.effect_reference = effect_reference
        job.effect_payload = effect_payload
        job.last_error = None
        job.completed_at = current
    elif job.attempts < job.max_attempts:
        job.state = "pending"
        job.available_at = current + timedelta(seconds=max(0, retry_delay_seconds))
        job.last_error = "verified_not_applied"
    else:
        job.state = "failed"
        job.last_error = "attempt_limit_reached"

    job.claim_token = None
    job.lease_until = None
    job.updated_at = current
    db.commit()
    db.refresh(job)
    return job


def cancel_outbox_action(
    db: Session,
    tenant: TenantContext,
    job_id: int,
    *,
    reason: str,
    now: datetime | None = None,
) -> tuple[ActionOutboxJob, bool]:
    """Cancel a pending/claimed job. Returns (job, cancelled). Never cancels executing/completed."""
    current = _utc_now(now)
    job = _load_locked_job(db, tenant, job_id)
    if job.state in ("executing", "completed", "unknown", "failed"):
        db.commit()
        return job, False
    if job.state == "cancelled":
        db.commit()
        return job, True
    job.state = "cancelled"
    job.last_error = reason.strip()[:120] or "cancelled"
    job.claim_token = None
    job.lease_until = None
    job.updated_at = current
    db.commit()
    db.refresh(job)
    return job, True
