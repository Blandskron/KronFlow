"""Templates, campaigns, approval snapshots, stub dispatch worker, and receipts (FK-30)."""

from datetime import datetime, timedelta, timezone
import hashlib
import html
import re
import secrets
from typing import Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import func, inspect, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.tenant_runtime import TenantRuntime
from app.public_models.unsubscribe import PublicUnsubscribeToken
from app.services.action_outbox_service import (
    claim_next_outbox_jobs,
    complete_outbox_action,
    enqueue_outbox_action,
)
from app.services.consent_authorization_service import (
    authorize_outbox_delivery,
    evaluate_persisted_consent,
    record_suppression,
)
from app.services.contact_points import normalize_email
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.campaigns import (
    Campaign,
    CampaignApproval,
    CampaignRecipient,
    ChannelEvent,
    DeliveryAttempt,
    MessageTemplate,
    TemplateVersion,
    TenantChannelConnection,
)
from app.tenant_models.contact_capture import ContactPoint
from app.tenant_models.operations import Cliente


TEMPLATE_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]{0,31})\s*\}\}")
UNSAFE_HTML_RE = re.compile(r"<\s*(?:script|iframe|object|embed)\b|javascript:|on[a-z]+\s*=", re.IGNORECASE)
RECEIPT_PRIORITY = {"queued": 0, "accepted": 1, "delivered": 2, "bounced": 3, "complained": 4, "unsubscribed": 5}


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Campaign timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def campaigns_ready(db: Session, tenant: TenantContext) -> bool:
    inspector = inspect(db.connection())
    return (
        inspector.has_table(MessageTemplate.__tablename__, schema=tenant.schema_name)
        and inspector.has_table(Campaign.__tablename__, schema=tenant.schema_name)
        and inspector.has_table(CampaignRecipient.__tablename__, schema=tenant.schema_name)
    )


def _require_ready(db: Session, tenant: TenantContext) -> None:
    if not campaigns_ready(db, tenant):
        raise HTTPException(status_code=503, detail="Campaign schema is unavailable")


def _validate_template_content(
    *,
    channel: str,
    subject: str | None,
    body_text: str,
    body_html: str | None,
    declared_variables: Sequence[str],
) -> list[str]:
    clean_text = body_text.strip()
    if not clean_text:
        raise HTTPException(status_code=422, detail="Template body_text must not be empty")
    if channel == "email" and (not subject or not subject.strip()):
        raise HTTPException(status_code=422, detail="Email templates require a non-empty subject")
    if body_html and UNSAFE_HTML_RE.search(body_html):
        raise HTTPException(status_code=422, detail="Template HTML contains disallowed active content")

    declared = sorted({v.strip() for v in declared_variables if v and v.strip()})
    used: set[str] = set()
    for content in (subject or "", clean_text, body_html or ""):
        used.update(TEMPLATE_VAR_RE.findall(content))
    undeclared = sorted(used - set(declared))
    if undeclared:
        raise HTTPException(status_code=422, detail=f"Undeclared template variables: {', '.join(undeclared)}")
    return declared


def render_template_preview(version: TemplateVersion, variables: dict[str, str]) -> dict:
    """Context-escaped preview rendering (HTML-escaped for body_html)."""
    def _sub_plain(match: re.Match[str]) -> str:
        return str(variables.get(match.group(1), ""))

    def _sub_html(match: re.Match[str]) -> str:
        return html.escape(str(variables.get(match.group(1), "")), quote=True)

    return {
        "subject": TEMPLATE_VAR_RE.sub(_sub_plain, version.subject) if version.subject else None,
        "body_text": TEMPLATE_VAR_RE.sub(_sub_plain, version.body_text),
        "body_html": TEMPLATE_VAR_RE.sub(_sub_html, version.body_html) if version.body_html else None,
    }


def create_template_with_version(
    db: Session,
    tenant: TenantContext,
    *,
    name: str,
    channel: str,
    language: str = "es",
    subject: str | None = None,
    body_text: str,
    body_html: str | None = None,
    declared_variables: Sequence[str] = (),
    approve_immediately: bool = False,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    norm_channel = channel.strip().lower()
    if norm_channel not in ("email", "whatsapp"):
        raise HTTPException(status_code=422, detail="channel must be 'email' or 'whatsapp'")
    clean_name = name.strip()
    if not clean_name or len(clean_name) > 120:
        raise HTTPException(status_code=422, detail="Template name must be 1..120 characters")
    declared = _validate_template_content(
        channel=norm_channel,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        declared_variables=declared_variables,
    )

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    tmpl = MessageTemplate(
        name=clean_name,
        channel=norm_channel,
        language=language.strip()[:16] or "es",
        created_by=actor_user_id[:64] if actor_user_id else None,
        created_at=current,
    )
    db.add(tmpl)
    db.flush()

    tv = TemplateVersion(
        template_id=tmpl.id,
        version=1,
        status="approved" if approve_immediately else "draft",
        subject=subject.strip()[:200] if subject else None,
        body_text=body_text.strip(),
        body_html=body_html,
        declared_variables=declared,
        approved_by=(actor_user_id[:64] if approve_immediately and actor_user_id else None),
        approved_at=current if approve_immediately else None,
        created_at=current,
    )
    db.add(tv)
    db.commit()
    db.refresh(tmpl)
    db.refresh(tv)
    return {
        "template_id": tmpl.id,
        "template_version_id": tv.id,
        "name": tmpl.name,
        "channel": tmpl.channel,
        "language": tmpl.language,
        "version": tv.version,
        "status": tv.status,
        "subject": tv.subject,
        "declared_variables": list(tv.declared_variables),
    }


def _validate_timezone(tz_name: str) -> str:
    clean = tz_name.strip()
    try:
        ZoneInfo(clean)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=422, detail=f"Invalid IANA timezone: {tz_name}")
    return clean


def _campaign_summary_in_tx(db: Session, campaign: Campaign) -> dict:
    counts_rows = db.execute(
        select(CampaignRecipient.status, func.count())
        .where(CampaignRecipient.campaign_id == campaign.id)
        .group_by(CampaignRecipient.status)
    ).all()
    counts = {status_name: int(cnt) for status_name, cnt in counts_rows}
    return {
        "id": campaign.id,
        "name": campaign.name,
        "channel": campaign.channel,
        "purpose": campaign.purpose,
        "template_version_id": campaign.template_version_id,
        "connection_id": campaign.connection_id,
        "timezone_iana": campaign.timezone_iana,
        "status": campaign.status,
        "version": campaign.version,
        "scheduled_at": campaign.scheduled_at,
        "recipient_counts": counts,
        "created_at": campaign.created_at,
        "updated_at": campaign.updated_at,
    }


def create_campaign(
    db: Session,
    tenant: TenantContext,
    *,
    name: str,
    channel: str,
    purpose: str,
    template_version_id: int,
    connection_id: int,
    segment_filter: dict | None = None,
    timezone_iana: str = "UTC",
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    norm_channel = channel.strip().lower()
    if norm_channel not in ("email", "whatsapp"):
        raise HTTPException(status_code=422, detail="channel must be 'email' or 'whatsapp'")
    clean_name = name.strip()
    clean_purpose = purpose.strip()
    if not clean_name or len(clean_name) > 140:
        raise HTTPException(status_code=422, detail="Campaign name must be 1..140 characters")
    if not clean_purpose or len(clean_purpose) > 64:
        raise HTTPException(status_code=422, detail="Campaign requires an explicit purpose")
    tz = _validate_timezone(timezone_iana)

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    tv = db.get(TemplateVersion, template_version_id)
    if tv is None or tv.status != "approved":
        raise HTTPException(status_code=422, detail="Campaign requires an approved template version")
    tmpl = db.get(MessageTemplate, tv.template_id)
    if tmpl is None or tmpl.channel != norm_channel:
        raise HTTPException(status_code=422, detail="Template channel does not match campaign channel")

    conn = db.get(TenantChannelConnection, connection_id)
    if conn is None or conn.channel != norm_channel:
        raise HTTPException(status_code=422, detail="Channel connection not found for campaign channel")
    if conn.status != "active" or not conn.verified:
        raise HTTPException(status_code=422, detail="Channel connection must be active and verified")
    if norm_channel == "whatsapp" and conn.provider != "stub":
        # Per 04-campaigns.md: real WhatsApp campaigns remain disabled until official adapter gate passes.
        raise HTTPException(status_code=422, detail="WhatsApp campaigns are restricted to stub demo mode")

    campaign = Campaign(
        name=clean_name,
        channel=norm_channel,
        purpose=clean_purpose,
        template_version_id=template_version_id,
        connection_id=connection_id,
        segment_filter=dict(segment_filter or {}),
        timezone_iana=tz,
        status="draft",
        version=1,
        created_by=actor_user_id[:64] if actor_user_id else None,
        created_at=current,
        updated_at=current,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return _campaign_summary_in_tx(db, campaign)


def approve_campaign(
    db: Session,
    tenant: TenantContext,
    campaign_id: int,
    *,
    expected_version: int,
    actor_user_id: str,
    scheduled_at: datetime | None = None,
    now: datetime | None = None,
) -> dict:
    """Freeze campaign approval, persist deduplicated eligible snapshot, and queue outbox jobs."""
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    campaign = db.scalar(select(Campaign).where(Campaign.id == campaign_id).with_for_update())
    if campaign is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.version != expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale campaign version")
    if campaign.status != "draft":
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Cannot approve campaign from status '{campaign.status}'")

    conn = db.get(TenantChannelConnection, campaign.connection_id)
    if conn is None or conn.status != "active" or not conn.verified:
        db.rollback()
        raise HTTPException(status_code=409, detail="Campaign connection is no longer active and verified")

    # Build deduplicated snapshot from verified active contact_points for this channel.
    points = list(
        db.scalars(
            select(ContactPoint)
            .where(
                ContactPoint.point_type == campaign.channel,
                ContactPoint.status == "active",
                ContactPoint.verified.is_(True),
            )
            .order_by(ContactPoint.id.asc())
        ).all()
    )

    ready_at = _now(scheduled_at) if scheduled_at is not None else current
    snapshot_count = 0
    seen_destinations: set[str] = set()

    for pt in points:
        if pt.normalized_value in seen_destinations:
            continue
        reason = evaluate_persisted_consent(
            db,
            tenant,
            client_id=pt.client_id,
            channel=campaign.channel,
            destination=pt.normalized_value,
            purpose=campaign.purpose,
            point_active=True,
            point_verified=True,
            now=current,
        )
        if reason != "eligible":
            continue
        seen_destinations.add(pt.normalized_value)

        job, _ = enqueue_outbox_action(
            db,
            tenant,
            action_type="campaign.delivery.send",
            idempotency_key=f"campaign:{campaign.id}:pt:{pt.id}",
            payload={
                "campaign_id": campaign.id,
                "contact_point_id": pt.id,
                "client_id": pt.client_id,
                "channel": campaign.channel,
                "destination": pt.normalized_value,
                "purpose": campaign.purpose,
                "connection_id": campaign.connection_id,
                "template_version_id": campaign.template_version_id,
            },
            available_at=ready_at,
            commit=False,
        )
        db.add(
            CampaignRecipient(
                campaign_id=campaign.id,
                contact_point_id=pt.id,
                client_id=pt.client_id,
                destination=pt.normalized_value,
                status="queued",
                outbox_job_id=job.id,
                updated_at=current,
            )
        )
        snapshot_count += 1

    campaign.version += 1
    campaign.scheduled_at = ready_at if scheduled_at is not None else None
    campaign.status = "scheduled" if (scheduled_at is not None and ready_at > current) else "running"
    campaign.updated_at = current

    db.add(
        CampaignApproval(
            campaign_id=campaign.id,
            campaign_version=campaign.version,
            template_version_id=campaign.template_version_id,
            connection_id=campaign.connection_id,
            snapshot_count=snapshot_count,
            approved_by=actor_user_id[:64],
            approved_at=current,
        )
    )
    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="campaign.approved",
        aggregate_type="campaign",
        aggregate_id=campaign.id,
        payload={"campaign_id": campaign.id, "snapshot_count": snapshot_count, "status": campaign.status},
        occurred_at=current,
    )
    db.commit()
    db.refresh(campaign)
    return _campaign_summary_in_tx(db, campaign)


def set_campaign_state(
    db: Session,
    tenant: TenantContext,
    campaign_id: int,
    *,
    action: str,
    expected_version: int,
    now: datetime | None = None,
) -> dict:
    """Pause, resume, or cancel a campaign with optimistic version check."""
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    campaign = db.scalar(select(Campaign).where(Campaign.id == campaign_id).with_for_update())
    if campaign is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.version != expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale campaign version")

    if action == "pause" and campaign.status in ("running", "scheduled"):
        campaign.status = "paused"
    elif action == "resume" and campaign.status == "paused":
        conn = db.get(TenantChannelConnection, campaign.connection_id)
        if conn is None or conn.status != "active" or not conn.verified:
            db.rollback()
            raise HTTPException(status_code=409, detail="Campaign connection is revoked or unverified")
        campaign.status = "running"
    elif action == "cancel" and campaign.status in ("draft", "approved", "scheduled", "running", "paused"):
        campaign.status = "cancelled"
    else:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Cannot '{action}' campaign from status '{campaign.status}'")

    campaign.version += 1
    campaign.updated_at = current
    db.commit()
    db.refresh(campaign)
    return _campaign_summary_in_tx(db, campaign)


def process_campaign_stub_batch(
    db: Session,
    tenant: TenantContext,
    *,
    limit: int = 20,
    now: datetime | None = None,
) -> dict:
    """Worker tick: claim outbox jobs, re-authorize consent/campaign/connection atomically, and dispatch via stub."""
    current = _now(now)
    claimed_jobs = claim_next_outbox_jobs(
        db, tenant, action_types=["campaign.delivery.send"], limit=limit, now=current,
    )
    accepted = 0
    suppressed = 0
    skipped_paused = 0

    for job in claimed_jobs:
        payload = job.payload or {}
        campaign_id = payload["campaign_id"]
        contact_point_id = payload["contact_point_id"]
        client_id = payload["client_id"]
        channel = payload["channel"]
        destination = payload["destination"]
        purpose = payload["purpose"]

        bind_tenant_session(db, tenant.schema_name)
        campaign = db.get(Campaign, campaign_id)
        recipient = db.scalar(
            select(CampaignRecipient).where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.contact_point_id == contact_point_id,
            )
        )
        conn = db.get(TenantChannelConnection, campaign.connection_id) if campaign else None

        # Respect pause/cancel/revoked connection before authorizing delivery.
        if campaign is None or campaign.status != "running" or conn is None or conn.status != "active":
            skipped_paused += 1
            if recipient is not None and campaign is not None and campaign.status == "cancelled":
                recipient.status = "suppressed"
                recipient.last_error = "campaign_cancelled"
                recipient.updated_at = current
                db.commit()
            continue

        auth = authorize_outbox_delivery(
            db,
            tenant,
            job_id=job.id,
            claim_token=job.claim_token,
            client_id=client_id,
            channel=channel,
            destination=destination,
            purpose=purpose,
            point_active=True,
            point_verified=True,
            now=current,
        )
        if not auth.authorized:
            suppressed += 1
            if recipient is not None:
                bind_tenant_session(db, tenant.schema_name)
                rec = db.get(CampaignRecipient, recipient.id)
                rec.status = "suppressed"
                rec.last_error = auth.reason
                rec.updated_at = current
                db.commit()
            continue

        # Stub provider dispatch (deterministic synthetic provider message ID).
        provider_msg_id = f"stub:{conn.provider}:c{campaign_id}:j{job.id}"
        complete_outbox_action(
            db,
            tenant,
            job.id,
            job.claim_token,
            effect_reference=provider_msg_id,
            effect_payload={"provider": conn.provider, "destination": destination, "status": "accepted"},
            now=current,
        )
        bind_tenant_session(db, tenant.schema_name)
        if recipient is not None:
            rec = db.get(CampaignRecipient, recipient.id)
            rec.status = "accepted"
            rec.provider_message_id = provider_msg_id
            rec.last_error = None
            rec.updated_at = current
            db.add(
                DeliveryAttempt(
                    campaign_recipient_id=rec.id,
                    attempt_number=job.attempts,
                    idempotency_key=job.idempotency_key,
                    provider=conn.provider,
                    provider_message_id=provider_msg_id,
                    outcome="accepted",
                    created_at=current,
                )
            )
            db.commit()
        accepted += 1

    return {"claimed": len(claimed_jobs), "accepted": accepted, "suppressed": suppressed, "skipped_paused": skipped_paused}


def ingest_channel_receipt(
    db: Session,
    tenant: TenantContext,
    *,
    provider_account_id: str,
    provider_event_id: str,
    event_type: str,
    provider_message_id: str | None = None,
    destination: str | None = None,
    payload: dict | None = None,
    occurred_at: datetime | None = None,
) -> dict:
    """Deduplicate provider receipts by (provider_account_id, provider_event_id) with monotonic status updates."""
    if event_type not in ("accepted", "delivered", "bounced", "complained", "unsubscribed"):
        raise HTTPException(status_code=422, detail=f"Unsupported receipt event_type: {event_type}")
    occ = _now(occurred_at)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    inserted_id = db.scalar(
        insert(ChannelEvent)
        .values(
            provider_account_id=provider_account_id.strip()[:80],
            provider_event_id=provider_event_id.strip()[:180],
            event_type=event_type,
            provider_message_id=provider_message_id,
            destination=destination,
            payload=dict(payload or {}),
            occurred_at=occ,
            recorded_at=occ,
        )
        .on_conflict_do_nothing(index_elements=["provider_account_id", "provider_event_id"])
        .returning(ChannelEvent.id)
    )
    if inserted_id is None:
        db.commit()
        return {"duplicate": True, "event_id": None}

    if provider_message_id:
        rec = db.scalar(
            select(CampaignRecipient).where(CampaignRecipient.provider_message_id == provider_message_id).with_for_update()
        )
        if rec is not None:
            current_prio = RECEIPT_PRIORITY.get(rec.status, 0)
            new_prio = RECEIPT_PRIORITY.get(event_type, 0)
            if new_prio > current_prio:
                rec.status = event_type
                rec.updated_at = occ
            if event_type in ("bounced", "complained", "unsubscribed"):
                campaign = db.get(Campaign, rec.campaign_id)
                reason_map = {"bounced": "hard_bounce", "complained": "complaint", "unsubscribed": "unsubscribe"}
                record_suppression(
                    db,
                    tenant,
                    channel=campaign.channel if campaign else "email",
                    destination=rec.destination,
                    purpose=campaign.purpose if (campaign and event_type == "unsubscribed") else None,
                    reason=reason_map[event_type],
                    source="provider_webhook",
                    client_id=rec.client_id,
                    recorded_at=occ,
                    commit=False,
                )

    db.commit()
    return {"duplicate": False, "event_id": inserted_id}


def record_public_unsubscribe(
    db: Session,
    tenant: TenantContext,
    *,
    channel: str,
    destination: str,
    purpose: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Idempotent generic unsubscribe that persists a durable suppression without revealing contact existence."""
    record_suppression(
        db,
        tenant,
        channel=channel,
        destination=destination,
        purpose=purpose,
        reason="unsubscribe",
        source="unsubscribe_link",
        recorded_at=_now(now),
        commit=True,
    )
    return {"status": "unsubscribed"}


def issue_unsubscribe_token(
    db: Session,
    tenant: TenantContext,
    *,
    channel: str,
    destination: str,
    purpose: str | None = None,
    client_id: int | None = None,
    ttl_days: int = 90,
    now: datetime | None = None,
) -> dict:
    """Issue a public opaque self-service unsubscribe token storing only its SHA-256 hash."""
    norm_channel = channel.strip().lower()
    if norm_channel not in ("email", "whatsapp"):
        raise HTTPException(status_code=422, detail="channel must be 'email' or 'whatsapp'")
    if norm_channel == "email":
        norm_dest = normalize_email(destination)
        if norm_dest is None:
            raise HTTPException(status_code=422, detail="Invalid email destination")
    else:
        norm_dest = destination.strip()
        if not norm_dest or len(norm_dest) > 255:
            raise HTTPException(status_code=422, detail="Invalid whatsapp destination")

    if not 1 <= ttl_days <= 365:
        raise HTTPException(status_code=422, detail="ttl_days must be between 1 and 365")

    norm_purpose = purpose.strip()[:64] if purpose and purpose.strip() else None
    current = _now(now)
    expires_at = current + timedelta(days=ttl_days)

    if client_id is not None:
        bind_tenant_session(db, tenant.schema_name)
        if db.get(Cliente, client_id) is None:
            raise HTTPException(status_code=404, detail="Contact not found")

    raw_token = f"unsub_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    row = PublicUnsubscribeToken(
        token_hash=token_hash,
        auth_tenant_id=tenant.auth_tenant_id,
        schema_name=tenant.schema_name,
        channel=norm_channel,
        destination=norm_dest,
        purpose=norm_purpose,
        client_id=client_id,
        expires_at=expires_at,
        created_at=current,
    )
    db.add(row)
    db.commit()
    return {
        "token": raw_token,
        "channel": norm_channel,
        "destination": norm_dest,
        "purpose": norm_purpose,
        "expires_at": expires_at,
    }


def redeem_unsubscribe_token(
    db: Session,
    raw_token: str,
    *,
    now: datetime | None = None,
) -> dict:
    """Redeem an opaque self-service unsubscribe token, suppressing and cancelling pending jobs atomically."""
    clean_token = raw_token.strip()
    if not clean_token:
        raise HTTPException(status_code=404, detail="Unsubscribe token not found or expired")
    token_hash = hashlib.sha256(clean_token.encode("utf-8")).hexdigest()
    current = _now(now)

    tok = db.scalar(
        select(PublicUnsubscribeToken)
        .where(PublicUnsubscribeToken.token_hash == token_hash)
        .with_for_update()
    )
    if tok is None or (tok.expires_at is not None and tok.expires_at <= current):
        db.rollback()
        raise HTTPException(status_code=404, detail="Unsubscribe token not found or expired")

    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == tok.auth_tenant_id))
    if runtime is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Unsubscribe token not found or expired")

    tenant = TenantContext(
        auth_tenant_id=runtime.auth_tenant_id,
        tenant_slug=runtime.tenant_slug,
        schema_name=runtime.schema_name,
        tenant_code=runtime.tenant_code,
        plan=runtime.plan,
        status=runtime.status,
    )
    record_suppression(
        db,
        tenant,
        channel=tok.channel,
        destination=tok.destination,
        purpose=tok.purpose,
        reason="unsubscribe",
        source="unsubscribe_link",
        client_id=tok.client_id,
        recorded_at=current,
        cancel_pending_jobs=True,
        commit=False,
    )
    if tok.used_at is None:
        tok.used_at = current
    db.commit()
    return {"status": "unsubscribed"}


def promote_due_scheduled_campaigns(
    db: Session,
    tenant: TenantContext,
    *,
    now: datetime | None = None,
) -> int:
    """Promote scheduled campaigns whose scheduled_at has arrived to running (or pause if connection invalid)."""
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    if not campaigns_ready(db, tenant):
        return 0

    due_campaigns = list(
        db.scalars(
            select(Campaign)
            .where(
                Campaign.status == "scheduled",
                Campaign.scheduled_at.is_not(None),
                Campaign.scheduled_at <= current,
            )
            .order_by(Campaign.id.asc())
            .with_for_update(skip_locked=True)
        ).all()
    )
    promoted = 0
    for campaign in due_campaigns:
        conn = db.get(TenantChannelConnection, campaign.connection_id)
        if conn is None or conn.status != "active" or not conn.verified:
            campaign.status = "paused"
            campaign.version += 1
            campaign.updated_at = current
            create_system_event(
                db,
                "campaign.schedule.blocked_connection",
                tenant.auth_tenant_id,
                tenant.schema_name,
                {"campaign_id": campaign.id, "connection_id": campaign.connection_id},
            )
            continue
        campaign.status = "running"
        campaign.version += 1
        campaign.updated_at = current
        publish_domain_event_in_tx(
            db,
            tenant,
            event_type="campaign.started",
            aggregate_type="campaign",
            aggregate_id=campaign.id,
            payload={
                "campaign_id": campaign.id,
                "scheduled_at": campaign.scheduled_at.isoformat() if campaign.scheduled_at else None,
            },
            occurred_at=current,
        )
        promoted += 1
    db.commit()
    return promoted


def preview_campaign_audience(
    db: Session,
    tenant: TenantContext,
    campaign_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    """Read-only audience pre-flight counting eligible destinations and exclusions by reason."""
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    points = list(
        db.scalars(
            select(ContactPoint)
            .where(
                ContactPoint.point_type == campaign.channel,
                ContactPoint.status == "active",
            )
            .order_by(ContactPoint.id.asc())
        ).all()
    )

    seen_destinations: set[str] = set()
    excluded_by_reason: dict[str, int] = {}
    sample_eligible: list[dict] = []
    eligible_count = 0

    for pt in points:
        if not pt.verified:
            excluded_by_reason["unverified_point"] = excluded_by_reason.get("unverified_point", 0) + 1
            continue
        if pt.normalized_value in seen_destinations:
            excluded_by_reason["duplicate_destination"] = excluded_by_reason.get("duplicate_destination", 0) + 1
            continue
        reason = evaluate_persisted_consent(
            db,
            tenant,
            client_id=pt.client_id,
            channel=campaign.channel,
            destination=pt.normalized_value,
            purpose=campaign.purpose,
            point_active=True,
            point_verified=True,
            now=current,
        )
        if reason != "eligible":
            excluded_by_reason[reason] = excluded_by_reason.get(reason, 0) + 1
            continue
        seen_destinations.add(pt.normalized_value)
        eligible_count += 1
        if len(sample_eligible) < 10:
            sample_eligible.append(
                {
                    "contact_point_id": pt.id,
                    "client_id": pt.client_id,
                    "destination": pt.normalized_value,
                }
            )

    total_candidates = len(points)
    return {
        "campaign_id": campaign.id,
        "channel": campaign.channel,
        "purpose": campaign.purpose,
        "total_candidates": total_candidates,
        "eligible_count": eligible_count,
        "excluded_count": total_candidates - eligible_count,
        "excluded_by_reason": excluded_by_reason,
        "sample_eligible": sample_eligible,
    }
