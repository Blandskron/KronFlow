import re
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import case, null, select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.system_event import SystemEvent
from app.schemas.contact_consent import ConsentEvidenceItem, ContactConsentOut
from app.services.ingest_service import ordered_consent_ready
from app.services.tenant_data import execute_for_tenant
from app.tenant_models.operations import Cliente
from app.tenant_models.whatsapp_consent import WhatsAppConsentState


DECISION_EVENT = "whatsapp.consent.changed"
PRIOR_WITHDRAWAL_EVENT = "whatsapp.consent.prior_withdrawal"
POLICY_VERSION = re.compile(r"v?[0-9]{1,8}(?:\.[0-9]{1,8}){0,3}")


def _policy(value: object) -> str | None:
    return value if isinstance(value, str) and len(value) <= 36 and POLICY_VERSION.fullmatch(value) else None


def _effective_date(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        date = datetime.fromisoformat(value)
    except ValueError:
        return None
    return date if date.utcoffset() is not None else None


def read_contact_consent(
    db: Session, tenant: TenantContext, contact_id: int, limit: int, before_id: int | None,
) -> ContactConsentOut:
    scope = (
        SystemEvent.auth_tenant_id == tenant.auth_tenant_id,
        SystemEvent.schema_name == tenant.schema_name,
        SystemEvent.payload["client_id"].astext == str(contact_id),
    )
    events = select(
        SystemEvent.id.label("event_id"), SystemEvent.event_type, SystemEvent.payload, SystemEvent.created_at,
    ).where(*scope, SystemEvent.event_type.in_((DECISION_EVENT, PRIOR_WITHDRAWAL_EVENT)))
    if before_id is not None:
        events = events.where(SystemEvent.id < before_id)
    page = events.order_by(SystemEvent.id.desc()).limit(limit + 1).subquery()
    ordered = ordered_consent_ready(db, tenant)
    decision = WhatsAppConsentState.decision_at if ordered else null()
    latest_event = select(SystemEvent.payload).where(*scope, SystemEvent.event_type == DECISION_EVENT).order_by(
        SystemEvent.id.desc(),
    ).limit(1).scalar_subquery()
    legacy_decision = case(
        (decision.is_(None) & Cliente.whatsapp_id.is_not(None) & ~Cliente.consentimiento_datos, latest_event),
    ).label("legacy_decision")
    statement = select(
        Cliente.whatsapp_id, Cliente.consentimiento_datos, Cliente.fecha_consentimiento, Cliente.version_politica,
        decision.label("decision_at"),
        (WhatsAppConsentState.authorized_from if ordered else null()).label("authorized_from"),
        legacy_decision, page,
    ).select_from(Cliente)
    if ordered:
        statement = statement.outerjoin(WhatsAppConsentState, WhatsAppConsentState.client_id == Cliente.id)
    rows = execute_for_tenant(db, tenant.schema_name, statement.outerjoin(
        page, Cliente.whatsapp_id.is_not(None) & (Cliente.whatsapp_id != ""),
    ).where(Cliente.id == contact_id).order_by(page.c.event_id.desc())).mappings().all()
    if not rows:
        raise HTTPException(status_code=404, detail="Contact not found")
    current = rows[0]
    if not current["whatsapp_id"]:
        return ContactConsentOut(state="unlinked", decision_at=None, authorized_from=None,
                                 policy_version=None, items=[], next_before_id=None)

    # A historical grant timestamp is usable only while the authorization remains active.
    granted = current["consentimiento_datos"] is True
    decision_at = current["decision_at"]
    if granted and decision_at is None:
        decision_at = current["fecha_consentimiento"]
    legacy = current["legacy_decision"]
    legacy_denial = isinstance(legacy, dict) and legacy.get("accepted") is False
    if legacy_denial:
        decision_at = _effective_date(legacy.get("decision_at"))
    state = "granted" if granted else "not_granted" if decision_at is not None or legacy_denial else "unrecorded"
    items = []
    for row in rows[:limit]:
        if row["event_id"] is None:
            continue
        payload = row["payload"] if isinstance(row["payload"], dict) else {}
        prior = row["event_type"] == PRIOR_WITHDRAWAL_EVENT
        accepted, source = payload.get("accepted"), payload.get("source")
        items.append(ConsentEvidenceItem(
            id=row["event_id"], kind="prior_withdrawal" if prior else "decision",
            accepted=accepted if not prior and isinstance(accepted, bool) else None,
            effective_at=_effective_date(payload.get("decision_at")), recorded_at=row["created_at"],
            policy_version=_policy(payload.get("policy_version")),
            source=source if source in ("operational", "whatsapp_message") else None,
        ))
    return ContactConsentOut(
        state=state, decision_at=decision_at, authorized_from=current["authorized_from"] if granted else None,
        policy_version=_policy(current["version_politica"]) if state != "unrecorded" else None,
        items=items, next_before_id=items[-1].id if len(rows) > limit else None,
    )
