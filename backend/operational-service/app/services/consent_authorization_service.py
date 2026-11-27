"""Transactional channel/purpose consent persistence and worker send authorization (FK-04)."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hmac

from fastapi import HTTPException
from sqlalchemy import inspect, or_, select, text, update
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.tenant_runtime import TenantRuntime
from app.services.campaign_eligibility import (
    CampaignRecipient,
    CampaignSuppression,
    Channel,
    ConsentDecision,
    ContactPointKey,
    ContactPointStatus,
    Reason,
    campaign_eligibility,
)
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.services.workflow_cancellation import cancel_waiting_runs_in_tx
from app.tenant_models.action_outbox import ActionOutboxJob
from app.tenant_models.campaigns import Campaign, CampaignRecipient as CampaignRecipientRow
from app.tenant_models.consent_ledger import ContactConsentDecision, ContactSuppression
from app.tenant_models.operations import Cliente


VALID_CHANNELS: tuple[Channel, ...] = ("email", "whatsapp")
VALID_DECISION_SOURCES = frozenset(
    {"operational", "whatsapp_message", "form", "unsubscribe_link", "provider_webhook", "import"}
)
VALID_LEGAL_BASES = frozenset({"consent", "contract", "legal_obligation", "legitimate_interest"})
VALID_SUPPRESSION_REASONS = frozenset({"unsubscribe", "baja", "hard_bounce", "complaint", "manual"})


@dataclass(frozen=True)
class DeliveryAuthorizationResult:
    authorized: bool
    reason: str
    job_state: str
    job_id: int


def _utc(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.utcoffset() is None:
        raise ValueError("Consent timestamps must include a time zone")
    return value.astimezone(timezone.utc)


def _normalize_channel(channel: str) -> Channel:
    normalized = channel.strip().lower()
    if normalized not in VALID_CHANNELS:
        raise ValueError(f"Unsupported consent channel: {channel!r}")
    return normalized  # type: ignore[return-value]


def _normalize_destination(channel: Channel, destination: str) -> str:
    cleaned = destination.strip()
    if not cleaned or len(cleaned) > 255:
        raise ValueError("Consent destination must be a non-empty string up to 255 characters")
    if channel == "email":
        # Preserve local-part case rules per 03-inbound-crm while normalizing domain case.
        if "@" in cleaned:
            local, domain = cleaned.rsplit("@", 1)
            return f"{local}@{domain.lower()}"
        return cleaned
    return cleaned


def _normalize_purpose(purpose: str) -> str:
    cleaned = purpose.strip()
    if not cleaned or cleaned != purpose or len(cleaned) > 64:
        raise ValueError("Consent requires an explicit trimmed purpose up to 64 characters")
    return cleaned


def consent_ledger_ready(db: Session, tenant: TenantContext) -> bool:
    inspector = inspect(db.connection())
    return (
        inspector.has_table(ContactConsentDecision.__tablename__, schema=tenant.schema_name)
        and inspector.has_table(ContactSuppression.__tablename__, schema=tenant.schema_name)
    )


def _require_consent_ledger_ready(db: Session, tenant: TenantContext) -> None:
    if not consent_ledger_ready(db, tenant):
        raise HTTPException(status_code=503, detail="Consent ledger schema is unavailable")


def lock_consent_scope(db: Session, schema_name: str, channel: Channel, destination: str) -> None:
    """Serialize consent/suppression writes and worker send authorization for the same contact point."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"flowkron-consent:{schema_name}:{channel}:{destination}"},
    )


def record_consent_decision(
    db: Session,
    tenant: TenantContext,
    *,
    client_id: int,
    channel: str,
    destination: str,
    purpose: str,
    granted: bool,
    effective_at: datetime,
    source: str,
    policy_version: str | None = None,
    legal_basis: str = "consent",
    notice_version: str | None = None,
    notice_hash: str | None = None,
    jurisdiction: str = "CL",
    actor_id: str | None = None,
    recorded_at: datetime | None = None,
    commit: bool = True,
) -> ContactConsentDecision:
    """Persist one channel/purpose consent decision under the scope lock."""
    norm_channel = _normalize_channel(channel)
    norm_destination = _normalize_destination(norm_channel, destination)
    norm_purpose = _normalize_purpose(purpose)
    if source not in VALID_DECISION_SOURCES:
        raise ValueError(f"Unsupported consent decision source: {source!r}")
    norm_basis = legal_basis.strip().lower()
    if norm_basis not in VALID_LEGAL_BASES:
        raise ValueError(f"Unsupported legal_basis: {legal_basis!r}")
    eff_utc = _utc(effective_at)
    rec_utc = _utc(recorded_at)

    bind_tenant_session(db, tenant.schema_name)
    _require_consent_ledger_ready(db, tenant)
    lock_consent_scope(db, tenant.schema_name, norm_channel, norm_destination)

    if db.get(Cliente, client_id) is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    row = ContactConsentDecision(
        client_id=client_id,
        channel=norm_channel,
        destination=norm_destination,
        purpose=norm_purpose,
        granted=bool(granted),
        effective_at=eff_utc,
        recorded_at=rec_utc,
        policy_version=policy_version.strip()[:36] if policy_version else None,
        legal_basis=norm_basis,
        notice_version=notice_version.strip()[:64] if notice_version else None,
        notice_hash=notice_hash.strip()[:64] if notice_hash else None,
        jurisdiction=(jurisdiction.strip().upper()[:16] or "CL"),
        source=source,
        actor_id=actor_id.strip()[:64] if actor_id else None,
    )
    db.add(row)
    db.flush()
    create_system_event(
        db,
        "consent.decision.recorded",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {
            "decision_id": row.id,
            "client_id": client_id,
            "channel": norm_channel,
            "purpose": norm_purpose,
            "granted": bool(granted),
            "effective_at": eff_utc.isoformat(),
            "policy_version": row.policy_version,
            "source": source,
        },
    )
    if not granted:
        publish_domain_event_in_tx(
            db,
            tenant,
            event_type="consent.withdrawn",
            aggregate_type="contact",
            aggregate_id=client_id,
            payload={"client_id": client_id, "channel": norm_channel, "purpose": norm_purpose},
            occurred_at=rec_utc,
        )
        cancel_waiting_runs_in_tx(
            db,
            tenant,
            event_type="consent.withdrawn",
            contact_id=client_id,
            reason="consent_withdrawn",
            now=rec_utc,
        )
    if commit:
        db.commit()
        db.refresh(row)
    return row


def record_suppression(
    db: Session,
    tenant: TenantContext,
    *,
    channel: str,
    destination: str,
    reason: str,
    source: str,
    purpose: str | None = None,
    client_id: int | None = None,
    actor_id: str | None = None,
    recorded_at: datetime | None = None,
    cancel_pending_jobs: bool = False,
    commit: bool = True,
) -> ContactSuppression:
    """Persist a durable suppression for a specific purpose or all purposes on a destination."""
    norm_channel = _normalize_channel(channel)
    norm_destination = _normalize_destination(norm_channel, destination)
    norm_purpose = _normalize_purpose(purpose) if purpose is not None else None
    if reason not in VALID_SUPPRESSION_REASONS:
        raise ValueError(f"Unsupported suppression reason: {reason!r}")
    rec_utc = _utc(recorded_at)

    bind_tenant_session(db, tenant.schema_name)
    _require_consent_ledger_ready(db, tenant)
    lock_consent_scope(db, tenant.schema_name, norm_channel, norm_destination)

    if client_id is not None and db.get(Cliente, client_id) is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    row = ContactSuppression(
        client_id=client_id,
        channel=norm_channel,
        destination=norm_destination,
        purpose=norm_purpose,
        reason=reason,
        source=source.strip()[:32] or "operational",
        recorded_at=rec_utc,
        actor_id=actor_id.strip()[:64] if actor_id else None,
    )
    db.add(row)
    db.flush()

    cancelled_jobs = 0
    if cancel_pending_jobs:
        inspector = inspect(db.connection())
        if inspector.has_table(ActionOutboxJob.__tablename__, schema=tenant.schema_name):
            job_conditions = [
                ActionOutboxJob.action_type == "campaign.delivery.send",
                ActionOutboxJob.state.in_(("pending", "claimed")),
                ActionOutboxJob.payload["channel"].astext == norm_channel,
                ActionOutboxJob.payload["destination"].astext == norm_destination,
            ]
            if norm_purpose is not None:
                job_conditions.append(ActionOutboxJob.payload["purpose"].astext == norm_purpose)
            res = db.execute(
                update(ActionOutboxJob)
                .where(*job_conditions)
                .values(
                    state="cancelled",
                    last_error=reason[:120],
                    claim_token=None,
                    lease_until=None,
                    updated_at=rec_utc,
                )
            )
            cancelled_jobs = int(res.rowcount or 0)

        if inspector.has_table(CampaignRecipientRow.__tablename__, schema=tenant.schema_name) and inspector.has_table(
            Campaign.__tablename__, schema=tenant.schema_name
        ):
            rec_conditions = [
                CampaignRecipientRow.status == "queued",
                CampaignRecipientRow.destination == norm_destination,
                Campaign.channel == norm_channel,
            ]
            if norm_purpose is not None:
                rec_conditions.append(Campaign.purpose == norm_purpose)
            matching_ids = select(CampaignRecipientRow.id).join(
                Campaign, Campaign.id == CampaignRecipientRow.campaign_id
            ).where(*rec_conditions)
            db.execute(
                update(CampaignRecipientRow)
                .where(CampaignRecipientRow.id.in_(matching_ids))
                .values(
                    status="suppressed",
                    last_error=reason[:120],
                    updated_at=rec_utc,
                )
            )

    create_system_event(
        db,
        "consent.suppression.recorded",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {
            "suppression_id": row.id,
            "client_id": client_id,
            "channel": norm_channel,
            "purpose": norm_purpose,
            "reason": reason,
            "source": row.source,
            "cancelled_pending_jobs": cancelled_jobs,
        },
    )
    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="contact.suppressed",
        aggregate_type="contact",
        aggregate_id=client_id if client_id is not None else norm_destination,
        payload={"client_id": client_id, "channel": norm_channel, "purpose": norm_purpose, "reason": reason},
        occurred_at=rec_utc,
    )
    cancel_waiting_runs_in_tx(
        db,
        tenant,
        event_type="contact.suppressed",
        contact_id=client_id,
        reason=f"suppressed:{reason}",
        now=rec_utc,
    )
    if commit:
        db.commit()
        db.refresh(row)
    return row


def _evaluate_persisted_consent_in_tx(
    db: Session,
    tenant: TenantContext,
    *,
    client_id: int,
    norm_channel: Channel,
    norm_destination: str,
    norm_purpose: str,
    point_active: bool,
    point_verified: bool,
    eval_now: datetime,
) -> Reason:
    point_key = ContactPointKey(tenant_id=tenant.auth_tenant_id, point_id=client_id, channel=norm_channel)
    recipient = CampaignRecipient(point=point_key, purpose=norm_purpose)
    client_exists = db.get(Cliente, client_id) is not None
    status = (
        ContactPointStatus(point=point_key, active=point_active, verified=point_verified)
        if client_exists
        else None
    )

    decision_rows = db.scalars(
        select(ContactConsentDecision).where(
            ContactConsentDecision.client_id == client_id,
            ContactConsentDecision.channel == norm_channel,
            ContactConsentDecision.destination == norm_destination,
            ContactConsentDecision.purpose == norm_purpose,
        )
    ).all()
    suppression_rows = db.scalars(
        select(ContactSuppression).where(
            ContactSuppression.channel == norm_channel,
            ContactSuppression.destination == norm_destination,
            or_(ContactSuppression.purpose.is_(None), ContactSuppression.purpose == norm_purpose),
        )
    ).all()

    decisions = [
        ConsentDecision(
            recipient=recipient,
            granted=row.granted,
            effective_at=row.effective_at,
            recorded_at=row.recorded_at,
        )
        for row in decision_rows
    ]
    suppressions = [
        CampaignSuppression(
            point=point_key,
            purpose=row.purpose,
            recorded_at=row.recorded_at,
        )
        for row in suppression_rows
    ]
    return campaign_eligibility(recipient, status, decisions, suppressions, now=eval_now)


def evaluate_persisted_consent(
    db: Session,
    tenant: TenantContext,
    *,
    client_id: int,
    channel: str,
    destination: str,
    purpose: str,
    point_active: bool = True,
    point_verified: bool = True,
    now: datetime | None = None,
) -> Reason:
    """Evaluate persisted consent decisions and suppressions through the canonical eligibility rules."""
    norm_channel = _normalize_channel(channel)
    norm_destination = _normalize_destination(norm_channel, destination)
    norm_purpose = _normalize_purpose(purpose)
    eval_now = _utc(now)

    bind_tenant_session(db, tenant.schema_name)
    _require_consent_ledger_ready(db, tenant)
    return _evaluate_persisted_consent_in_tx(
        db,
        tenant,
        client_id=client_id,
        norm_channel=norm_channel,
        norm_destination=norm_destination,
        norm_purpose=norm_purpose,
        point_active=point_active,
        point_verified=point_verified,
        eval_now=eval_now,
    )


def authorize_outbox_delivery(
    db: Session,
    tenant: TenantContext,
    *,
    job_id: int,
    claim_token: str,
    client_id: int,
    channel: str,
    destination: str,
    purpose: str,
    point_active: bool = True,
    point_verified: bool = True,
    now: datetime | None = None,
) -> DeliveryAuthorizationResult:
    """Atomically verify tenant runtime + consent/suppression and transition outbox job to executing."""
    norm_channel = _normalize_channel(channel)
    norm_destination = _normalize_destination(norm_channel, destination)
    norm_purpose = _normalize_purpose(purpose)
    current = _utc(now)

    bind_tenant_session(db, tenant.schema_name)
    _require_consent_ledger_ready(db, tenant)
    if not inspect(db.connection()).has_table(ActionOutboxJob.__tablename__, schema=tenant.schema_name):
        raise HTTPException(status_code=503, detail="Action outbox schema is unavailable")

    # Serialize with concurrent consent updates / suppressions for this exact destination.
    lock_consent_scope(db, tenant.schema_name, norm_channel, norm_destination)

    runtime = db.scalar(
        select(TenantRuntime).where(TenantRuntime.auth_tenant_id == tenant.auth_tenant_id)
    )
    job = db.scalar(select(ActionOutboxJob).where(ActionOutboxJob.id == job_id).with_for_update())
    if job is None:
        raise HTTPException(status_code=404, detail="Outbox job not found")
    if not job.claim_token or not hmac.compare_digest(job.claim_token, claim_token):
        raise HTTPException(status_code=409, detail="Stale outbox claim")
    if job.lease_until is None or job.lease_until <= current:
        raise HTTPException(status_code=409, detail="Outbox claim expired")
    if job.state != "claimed":
        raise HTTPException(status_code=409, detail=f"Cannot authorize delivery from state '{job.state}'")

    if runtime is not None and runtime.status != "active":
        job.state = "cancelled"
        job.last_error = "tenant_suspended"
        job.claim_token = None
        job.lease_until = None
        job.updated_at = current
        db.commit()
        return DeliveryAuthorizationResult(
            authorized=False,
            reason="tenant_suspended",
            job_state=job.state,
            job_id=job.id,
        )

    reason = _evaluate_persisted_consent_in_tx(
        db,
        tenant,
        client_id=client_id,
        norm_channel=norm_channel,
        norm_destination=norm_destination,
        norm_purpose=norm_purpose,
        point_active=point_active,
        point_verified=point_verified,
        eval_now=current,
    )
    if reason != "eligible":
        job.state = "cancelled"
        job.last_error = reason
        job.claim_token = None
        job.lease_until = None
        job.updated_at = current
        db.commit()
        return DeliveryAuthorizationResult(
            authorized=False,
            reason=reason,
            job_state=job.state,
            job_id=job.id,
        )

    job.state = "executing"
    job.updated_at = current
    db.commit()
    return DeliveryAuthorizationResult(
        authorized=True,
        reason="eligible",
        job_state=job.state,
        job_id=job.id,
    )


def build_ts27560_consent_receipt(
    decision: ContactConsentDecision,
    *,
    tenant_slug: str,
    controller_name: str | None = None,
    dpo_contact_email: str | None = None,
) -> dict:
    """Build an ISO/IEC TS 27560:2023 interoperable consent receipt from a ledger decision (PRV-011)."""
    return {
        "schemaVersion": "ISO/IEC TS 27560:2023",
        "recordId": f"urn:kronflow:{tenant_slug}:consent:{decision.id}",
        "piiPrincipalId": f"contact:{decision.client_id}",
        "jurisdiction": decision.jurisdiction or "CL",
        "collectionMethod": decision.source,
        "piiControllers": [
            {
                "piiController": controller_name or tenant_slug,
                "contact": dpo_contact_email or "",
            }
        ],
        "services": [
            {
                "service": f"kronflow:{decision.channel}",
                "channel": decision.channel,
                "destination": decision.destination,
                "purposes": [
                    {
                        "purpose": decision.purpose,
                        "lawfulBasis": decision.legal_basis or "consent",
                        "consentType": "explicit" if (decision.legal_basis or "consent") == "consent" else "non_consent",
                        "status": "granted" if decision.granted else "withdrawn",
                        "effectiveAt": decision.effective_at.isoformat(),
                        "recordedAt": decision.recorded_at.isoformat(),
                        "policyVersion": decision.policy_version,
                        "noticeVersion": decision.notice_version,
                        "noticeHash": decision.notice_hash,
                    }
                ],
            }
        ],
    }


def list_contact_consent_receipts(db: Session, tenant: TenantContext, contact_id: int) -> list[dict]:
    bind_tenant_session(db, tenant.schema_name)
    _require_consent_ledger_ready(db, tenant)
    if db.get(Cliente, contact_id) is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    rows = list(
        db.scalars(
            select(ContactConsentDecision)
            .where(ContactConsentDecision.client_id == contact_id)
            .order_by(ContactConsentDecision.effective_at.desc(), ContactConsentDecision.id.desc())
        ).all()
    )
    return [build_ts27560_consent_receipt(row, tenant_slug=tenant.tenant_slug) for row in rows]


def record_omnichannel_revocation(
    db: Session,
    tenant: TenantContext,
    *,
    client_id: int,
    purpose: str | None = None,
    reason: str = "baja",
    source: str = "operational",
    actor_id: str | None = None,
    recorded_at: datetime | None = None,
    cancel_pending_jobs: bool = True,
    commit: bool = True,
) -> dict:
    """Propagate a revocation across ALL known email and WhatsApp destinations of a contact (PRV-011)."""
    from app.tenant_models.contact_capture import ContactPoint

    rec_utc = _utc(recorded_at)
    bind_tenant_session(db, tenant.schema_name)
    _require_consent_ledger_ready(db, tenant)
    client = db.get(Cliente, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    targets: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(ch: str, dest: str | None) -> None:
        if not dest or not dest.strip() or dest.strip().startswith("anon:"):
            return
        norm = _normalize_destination(_normalize_channel(ch), dest)
        key = (ch, norm)
        if key not in seen:
            seen.add(key)
            targets.append(key)

    _add("email", client.email)
    _add("whatsapp", client.whatsapp_id)
    if inspect(db.connection()).has_table(ContactPoint.__tablename__, schema=tenant.schema_name):
        for pt in db.scalars(select(ContactPoint).where(ContactPoint.client_id == client_id)).all():
            if pt.point_type == "email":
                _add("email", pt.normalized_value)
            elif pt.point_type in ("whatsapp", "phone"):
                _add("whatsapp", pt.normalized_value)

    suppressed_channels: list[dict[str, str]] = []
    for ch, dest in targets:
        record_suppression(
            db,
            tenant,
            channel=ch,
            destination=dest,
            purpose=purpose,
            reason=reason,
            source=source,
            client_id=client_id,
            actor_id=actor_id,
            recorded_at=rec_utc,
            cancel_pending_jobs=cancel_pending_jobs,
            commit=False,
        )
        suppressed_channels.append({"channel": ch, "destination": dest})

    if commit:
        db.commit()
    return {
        "client_id": client_id,
        "purpose": purpose,
        "suppressed_count": len(suppressed_channels),
        "suppressed_channels": suppressed_channels,
    }
