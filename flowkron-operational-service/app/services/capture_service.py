"""Multichannel contact points, repeatable backfill, public forms (FK-28) and scoped credentials (FK-12)."""

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import secrets
from typing import Sequence
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.security import hash_secret, verify_secret
from app.core.tenant_resolver import TenantContext
from app.public_models.capture_access import PublicCaptureForm, ScopedIntegrationCredential
from app.public_models.tenant_runtime import TenantRuntime
from app.services.consent_authorization_service import record_consent_decision
from app.services.contact_points import normalize_email, normalize_phone
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.contact_capture import ContactPoint, LeadCapture
from app.tenant_models.operations import Cliente, Lead


ALLOWED_SCOPES = frozenset({"leads:create"})
DEFAULT_FORM_FIELDS = ["name", "email", "phone", "message", "marketing_opt_in"]


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Capture timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _payload_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def capture_tables_ready(db: Session, tenant: TenantContext) -> bool:
    inspector = inspect(db.connection())
    return (
        inspector.has_table(ContactPoint.__tablename__, schema=tenant.schema_name)
        and inspector.has_table(LeadCapture.__tablename__, schema=tenant.schema_name)
    )


def _require_ready(db: Session, tenant: TenantContext) -> None:
    if not capture_tables_ready(db, tenant):
        raise HTTPException(status_code=503, detail="Contact capture schema is unavailable")


def backfill_contact_points(db: Session, tenant: TenantContext) -> dict:
    """Idempotent additive backfill from Cliente into contact_points, quarantining collisions."""
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    clients = list(db.scalars(select(Cliente).order_by(Cliente.id.asc())).all())
    candidates: dict[tuple[str, str], list[int]] = defaultdict(list)
    unresolved = 0

    for client in clients:
        if client.email:
            norm = normalize_email(client.email)
            if norm:
                candidates[("email", norm)].append(client.id)
            else:
                unresolved += 1
        if client.telefono:
            norm = normalize_phone(client.telefono)
            if norm:
                candidates[("phone", norm)].append(client.id)
            else:
                unresolved += 1
        if client.whatsapp_id:
            raw_wa = client.whatsapp_id.strip()
            norm_wa = normalize_phone(raw_wa if raw_wa.startswith("+") else f"+{raw_wa}")
            if norm_wa:
                candidates[("whatsapp", norm_wa)].append(client.id)
            else:
                unresolved += 1

    inserted = 0
    skipped_existing = 0
    collisions = 0
    now = _now()

    for (point_type, normalized_value), client_ids in sorted(candidates.items()):
        unique_ids = sorted(set(client_ids))
        if len(unique_ids) > 1:
            collisions += 1
            continue
        target_client_id = unique_ids[0]
        existing = db.scalar(
            select(ContactPoint).where(
                ContactPoint.point_type == point_type,
                ContactPoint.normalized_value == normalized_value,
            )
        )
        if existing is not None:
            if existing.client_id != target_client_id:
                collisions += 1
            else:
                skipped_existing += 1
            continue
        db.add(
            ContactPoint(
                client_id=target_client_id,
                point_type=point_type,
                normalized_value=normalized_value,
                status="active",
                verified=False,
                source="backfill",
                created_at=now,
            )
        )
        inserted += 1

    db.commit()
    return {
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "collisions": collisions,
        "unresolved": unresolved,
    }


def issue_scoped_credential(
    db: Session,
    tenant: TenantContext,
    *,
    name: str,
    scopes: Sequence[str],
    expires_at: datetime | None = None,
    created_by: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Issue a scoped server-to-server credential (FK-12), returning the raw secret once."""
    clean_name = name.strip()
    if not clean_name or len(clean_name) > 80:
        raise HTTPException(status_code=422, detail="Credential name must be 1..80 characters")
    clean_scopes = sorted({s.strip() for s in scopes if s and s.strip()})
    if not clean_scopes or not set(clean_scopes).issubset(ALLOWED_SCOPES):
        raise HTTPException(status_code=422, detail=f"Supported scopes: {sorted(ALLOWED_SCOPES)}")

    current = _now(now)
    expiry = _now(expires_at) if expires_at is not None else None
    if expiry is not None and expiry <= current:
        raise HTTPException(status_code=422, detail="expires_at must be in the future")

    prefix = f"fki_{secrets.token_hex(6)}"
    secret = secrets.token_urlsafe(32)
    raw_key = f"{prefix}.{secret}"

    cred = ScopedIntegrationCredential(
        auth_tenant_id=tenant.auth_tenant_id,
        schema_name=tenant.schema_name,
        name=clean_name,
        key_prefix=prefix,
        key_hash=hash_secret(raw_key),
        scopes=clean_scopes,
        expires_at=expiry,
        created_by=created_by[:64] if created_by else None,
        created_at=current,
    )
    db.add(cred)
    db.flush()
    create_system_event(
        db,
        "integration.credential.issued",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"credential_id": cred.id, "key_prefix": prefix, "scopes": clean_scopes},
    )
    db.commit()
    db.refresh(cred)
    return {
        "id": cred.id,
        "name": cred.name,
        "key_prefix": cred.key_prefix,
        "api_key": raw_key,
        "scopes": list(cred.scopes),
        "expires_at": cred.expires_at,
        "revoked_at": cred.revoked_at,
        "created_at": cred.created_at,
    }


def revoke_scoped_credential(
    db: Session,
    tenant: TenantContext,
    credential_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    current = _now(now)
    cred = db.scalar(
        select(ScopedIntegrationCredential).where(
            ScopedIntegrationCredential.id == credential_id,
            ScopedIntegrationCredential.auth_tenant_id == tenant.auth_tenant_id,
        )
    )
    if cred is None:
        raise HTTPException(status_code=404, detail="Scoped credential not found")
    if cred.revoked_at is None:
        cred.revoked_at = current
        create_system_event(
            db,
            "integration.credential.revoked",
            tenant.auth_tenant_id,
            tenant.schema_name,
            {"credential_id": cred.id, "key_prefix": cred.key_prefix},
        )
        db.commit()
        db.refresh(cred)
    return {
        "id": cred.id,
        "name": cred.name,
        "key_prefix": cred.key_prefix,
        "scopes": list(cred.scopes),
        "expires_at": cred.expires_at,
        "revoked_at": cred.revoked_at,
    }


def authenticate_scoped_credential(
    db: Session,
    raw_key: str | None,
    *,
    required_scope: str,
    now: datetime | None = None,
) -> tuple[TenantContext, ScopedIntegrationCredential]:
    """Authenticate a scoped credential and resolve its active tenant context."""
    if not raw_key or "." not in raw_key:
        raise HTTPException(status_code=401, detail="Invalid integration credential")
    prefix = raw_key.split(".", 1)[0]
    cred = db.scalar(select(ScopedIntegrationCredential).where(ScopedIntegrationCredential.key_prefix == prefix))
    if cred is None or not verify_secret(raw_key, cred.key_hash):
        raise HTTPException(status_code=401, detail="Invalid integration credential")

    current = _now(now)
    if cred.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Integration credential has been revoked")
    if cred.expires_at is not None and cred.expires_at <= current:
        raise HTTPException(status_code=401, detail="Integration credential has expired")
    if required_scope not in (cred.scopes or []):
        raise HTTPException(status_code=403, detail=f"Missing required scope '{required_scope}'")

    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == cred.auth_tenant_id))
    if runtime is None or runtime.status != "active":
        raise HTTPException(status_code=403, detail="Tenant runtime is not active")

    tenant = TenantContext(
        auth_tenant_id=runtime.auth_tenant_id,
        tenant_slug=runtime.tenant_slug,
        schema_name=runtime.schema_name,
        tenant_code=runtime.tenant_code,
        plan=runtime.plan,
        status=runtime.status,
    )
    return tenant, cred


def create_public_form(
    db: Session,
    tenant: TenantContext,
    *,
    name: str,
    source_label: str = "web_form",
    allowed_fields: Sequence[str] | None = None,
    created_by: str | None = None,
) -> dict:
    clean_name = name.strip()
    if not clean_name or len(clean_name) > 80:
        raise HTTPException(status_code=422, detail="Form name must be 1..80 characters")
    fields = list(allowed_fields) if allowed_fields else list(DEFAULT_FORM_FIELDS)
    token = f"frm_{secrets.token_urlsafe(24)}"
    form = PublicCaptureForm(
        auth_tenant_id=tenant.auth_tenant_id,
        schema_name=tenant.schema_name,
        name=clean_name,
        form_token=token,
        source_label=source_label.strip()[:48] or "web_form",
        allowed_fields=fields,
        is_active=True,
        created_by=created_by[:64] if created_by else None,
    )
    db.add(form)
    db.commit()
    db.refresh(form)
    return {
        "id": form.id,
        "name": form.name,
        "form_token": form.form_token,
        "source_label": form.source_label,
        "allowed_fields": list(form.allowed_fields),
        "is_active": form.is_active,
        "created_at": form.created_at,
    }


def resolve_public_form(db: Session, form_token: str) -> tuple[TenantContext, PublicCaptureForm]:
    form = db.scalar(select(PublicCaptureForm).where(PublicCaptureForm.form_token == form_token.strip()))
    if form is None or not form.is_active:
        raise HTTPException(status_code=404, detail="Form not found")
    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == form.auth_tenant_id))
    if runtime is None or runtime.status != "active":
        raise HTTPException(status_code=404, detail="Form not found")
    return (
        TenantContext(
            auth_tenant_id=runtime.auth_tenant_id,
            tenant_slug=runtime.tenant_slug,
            schema_name=runtime.schema_name,
            tenant_code=runtime.tenant_code,
            plan=runtime.plan,
            status=runtime.status,
        ),
        form,
    )


def capture_lead(
    db: Session,
    tenant: TenantContext,
    *,
    source_kind: str,
    source_ref: str,
    idempotency_key: str,
    name: str,
    email: str | None = None,
    phone: str | None = None,
    message: str | None = None,
    marketing_opt_in: bool = False,
    honeypot: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Idempotently capture a lead, match/create canonical contact_points, and emit domain events."""
    if source_kind not in ("integration", "public_form"):
        raise ValueError("source_kind must be 'integration' or 'public_form'")
    if source_kind == "public_form" and honeypot and honeypot.strip():
        # Silent generic acceptance for bots without polluting CRM.
        return {"status": "accepted", "capture_id": None, "duplicate": False}

    clean_name = name.strip()
    if not clean_name or len(clean_name) > 160:
        raise HTTPException(status_code=422, detail="name must be 1..160 characters")
    norm_email = normalize_email(email) if email else None
    norm_phone = normalize_phone(phone) if phone else None
    if email and norm_email is None:
        raise HTTPException(status_code=422, detail="Invalid email format")
    if phone and norm_phone is None:
        raise HTTPException(status_code=422, detail="Phone must include an explicit international + prefix")
    if norm_email is None and norm_phone is None:
        raise HTTPException(status_code=422, detail="At least one valid email or phone is required")

    clean_key = idempotency_key.strip()[:180]
    if not clean_key:
        raise HTTPException(status_code=422, detail="idempotency_key is required")

    digest = _payload_hash(
        {
            "name": clean_name,
            "email": norm_email,
            "phone": norm_phone,
            "message": message.strip() if message else None,
            "marketing_opt_in": bool(marketing_opt_in),
        }
    )
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    existing_capture = db.scalar(
        select(LeadCapture).where(
            LeadCapture.source_kind == source_kind,
            LeadCapture.source_ref == source_ref,
            LeadCapture.idempotency_key == clean_key,
        )
    )
    if existing_capture is not None:
        if source_kind == "integration" and existing_capture.payload_hash != digest:
            raise HTTPException(status_code=409, detail="Idempotency key reused with a different payload")
        return {
            "status": "accepted",
            "capture_id": None if source_kind == "public_form" else existing_capture.id,
            "duplicate": True,
        }

    matched_points: list[ContactPoint] = []
    if norm_email is not None:
        pt = db.scalar(
            select(ContactPoint).where(ContactPoint.point_type == "email", ContactPoint.normalized_value == norm_email)
        )
        if pt is not None:
            matched_points.append(pt)
    if norm_phone is not None:
        pt = db.scalar(
            select(ContactPoint).where(ContactPoint.point_type == "phone", ContactPoint.normalized_value == norm_phone)
        )
        if pt is not None:
            matched_points.append(pt)

    matched_client_ids = sorted({pt.client_id for pt in matched_points})
    contact_created = False

    if len(matched_client_ids) > 1:
        # Conflicting contact points: record for review without merging or leaking existence.
        capture = LeadCapture(
            source_kind=source_kind,
            source_ref=source_ref,
            idempotency_key=clean_key,
            payload_hash=digest,
            client_id=None,
            lead_id=None,
            status="conflict_review",
            conflict_details={"matched_client_ids": matched_client_ids},
            created_at=current,
        )
        db.add(capture)
        db.flush()
        db.commit()
        return {
            "status": "accepted",
            "capture_id": None if source_kind == "public_form" else capture.id,
            "duplicate": False,
        }

    if len(matched_client_ids) == 1:
        client = db.get(Cliente, matched_client_ids[0])
    else:
        client = Cliente(
            rut=f"crm:{uuid4().hex}",
            nombre=clean_name,
            email=norm_email,
            telefono=norm_phone,
            canal_origen=source_kind,
            consentimiento_datos=False,
        )
        db.add(client)
        db.flush()
        contact_created = True

    # Attach any new normalized points to the resolved client.
    for pt_type, pt_val in (("email", norm_email), ("phone", norm_phone)):
        if pt_val is None:
            continue
        db.execute(
            insert(ContactPoint)
            .values(
                client_id=client.id,
                point_type=pt_type,
                normalized_value=pt_val,
                status="active",
                verified=False,
                source=source_kind,
                created_at=current,
            )
            .on_conflict_do_nothing(index_elements=["point_type", "normalized_value"])
        )

    lead = Lead(
        cliente_id=client.id,
        estado="nuevo",
        clasificacion="tibio",
        resumen_ia=message.strip()[:2000] if message else None,
    )
    db.add(lead)
    db.flush()

    capture = LeadCapture(
        source_kind=source_kind,
        source_ref=source_ref,
        idempotency_key=clean_key,
        payload_hash=digest,
        client_id=client.id,
        lead_id=lead.id,
        status="accepted",
        created_at=current,
    )
    db.add(capture)
    db.flush()

    if marketing_opt_in and norm_email is not None:
        record_consent_decision(
            db,
            tenant,
            client_id=client.id,
            channel="email",
            destination=norm_email,
            purpose="marketing",
            granted=True,
            effective_at=current,
            recorded_at=current,
            source="form",
            policy_version="v1.0",
            commit=False,
        )

    if contact_created:
        publish_domain_event_in_tx(
            db,
            tenant,
            event_type="contact.created",
            aggregate_type="contact",
            aggregate_id=client.id,
            payload={"contact_id": client.id, "source": source_kind},
            occurred_at=current,
        )
    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="lead.captured",
        aggregate_type="lead",
        aggregate_id=lead.id,
        payload={"lead_id": lead.id, "contact_id": client.id, "capture_id": capture.id, "source": source_kind},
        occurred_at=current,
    )
    db.commit()
    return {
        "status": "accepted",
        "capture_id": None if source_kind == "public_form" else capture.id,
        "duplicate": False,
    }
