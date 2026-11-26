"""Authorized contact identity merge preserving active suppressions, history, and aliases."""

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import inspect, select, update
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.contact import ContactMergeIn
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.consent_ledger import ContactConsentDecision, ContactSuppression
from app.tenant_models.contact_capture import ContactPoint, LeadCapture
from app.tenant_models.operations import Cliente, Lead
from app.tenant_models.opportunity import Opportunity
from app.tenant_models.phase4_hub import WebchatSession
from app.tenant_models.phase5_integrations import ExternalEntityMapping
from app.tenant_models.phase6_extensions import CommerceOrder, VoiceCallSession


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Merge timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def merge_contacts(
    db: Session,
    tenant: TenantContext,
    source_contact_id: int,
    payload: ContactMergeIn,
    *,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Explicit confirmation is required to merge contacts")
    target_contact_id = payload.target_contact_id
    if source_contact_id == target_contact_id:
        raise HTTPException(status_code=422, detail="Source and target contact IDs must be different")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)

    low_id, high_id = sorted((source_contact_id, target_contact_id))
    low_row = db.scalar(select(Cliente).where(Cliente.id == low_id).with_for_update())
    high_row = db.scalar(select(Cliente).where(Cliente.id == high_id).with_for_update())
    source = low_row if low_id == source_contact_id else high_row
    target = high_row if low_id == source_contact_id else low_row
    if source is None or target is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Source or target contact not found")

    existing_tables = set(inspect(db.connection()).get_table_names(schema=tenant.schema_name))

    preserved_aliases = {
        "rut": source.rut,
        "whatsapp_id": source.whatsapp_id,
        "email": source.email,
        "phone": source.telefono,
    }
    if not target.email and source.email:
        target.email = source.email
    if not target.telefono and source.telefono:
        target.telefono = source.telefono
    if not target.whatsapp_id and source.whatsapp_id:
        target.whatsapp_id = source.whatsapp_id
    target.actualizado_en = current

    leads_moved = int(
        db.execute(update(Lead).where(Lead.cliente_id == source_contact_id).values(cliente_id=target_contact_id)).rowcount or 0
    )

    opportunities_moved = 0
    if Opportunity.__tablename__ in existing_tables:
        opportunities_moved = int(
            db.execute(
                update(Opportunity).where(Opportunity.contact_id == source_contact_id).values(contact_id=target_contact_id)
            ).rowcount
            or 0
        )

    if LeadCapture.__tablename__ in existing_tables:
        db.execute(
            update(LeadCapture).where(LeadCapture.client_id == source_contact_id).values(client_id=target_contact_id)
        )

    consents_moved = 0
    if ContactConsentDecision.__tablename__ in existing_tables:
        consents_moved = int(
            db.execute(
                update(ContactConsentDecision)
                .where(ContactConsentDecision.client_id == source_contact_id)
                .values(client_id=target_contact_id)
            ).rowcount
            or 0
        )

    suppressions_moved = 0
    if ContactSuppression.__tablename__ in existing_tables:
        suppressions_moved = int(
            db.execute(
                update(ContactSuppression)
                .where(ContactSuppression.client_id == source_contact_id)
                .values(client_id=target_contact_id)
            ).rowcount
            or 0
        )

    webchat_sessions_moved = 0
    if WebchatSession.__tablename__ in existing_tables:
        webchat_sessions_moved = int(
            db.execute(
                update(WebchatSession).where(WebchatSession.client_id == source_contact_id).values(client_id=target_contact_id)
            ).rowcount
            or 0
        )

    orders_moved = 0
    if CommerceOrder.__tablename__ in existing_tables:
        orders_moved = int(
            db.execute(
                update(CommerceOrder).where(CommerceOrder.client_id == source_contact_id).values(client_id=target_contact_id)
            ).rowcount
            or 0
        )

    voice_calls_moved = 0
    if VoiceCallSession.__tablename__ in existing_tables:
        voice_calls_moved = int(
            db.execute(
                update(VoiceCallSession)
                .where(VoiceCallSession.client_id == source_contact_id)
                .values(client_id=target_contact_id)
            ).rowcount
            or 0
        )

    mappings_moved = 0
    if ExternalEntityMapping.__tablename__ in existing_tables:
        mappings_moved = int(
            db.execute(
                update(ExternalEntityMapping)
                .where(
                    ExternalEntityMapping.local_type == "contact",
                    ExternalEntityMapping.local_id == str(source_contact_id),
                )
                .values(local_id=str(target_contact_id))
            ).rowcount
            or 0
        )

    contact_points_moved = 0
    contact_points_deduped = 0
    if ContactPoint.__tablename__ in existing_tables:
        source_points = list(
            db.scalars(select(ContactPoint).where(ContactPoint.client_id == source_contact_id)).all()
        )
        for pt in source_points:
            existing_target_pt = db.scalar(
                select(ContactPoint).where(
                    ContactPoint.client_id == target_contact_id,
                    ContactPoint.point_type == pt.point_type,
                    ContactPoint.normalized_value == pt.normalized_value,
                )
            )
            if existing_target_pt is not None:
                if pt.verified and not existing_target_pt.verified:
                    existing_target_pt.verified = True
                db.delete(pt)
                contact_points_deduped += 1
            else:
                pt.client_id = target_contact_id
                contact_points_moved += 1

    db.flush()
    db.delete(source)
    db.flush()

    event_payload = {
        "source_contact_id": source_contact_id,
        "target_contact_id": target_contact_id,
        "actor_user_id": actor_user_id,
        "reason": payload.reason.strip(),
        "suppressions_moved": suppressions_moved,
        "preserved_aliases": preserved_aliases,
    }
    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="contact.merged",
        aggregate_type="contact",
        aggregate_id=target_contact_id,
        payload=event_payload,
        occurred_at=current,
    )
    create_system_event(db, "crm.contact.merged", tenant.auth_tenant_id, tenant.schema_name, event_payload)
    db.commit()

    return {
        "source_contact_id": source_contact_id,
        "target_contact_id": target_contact_id,
        "leads_moved": leads_moved,
        "opportunities_moved": opportunities_moved,
        "contact_points_moved": contact_points_moved,
        "contact_points_deduped": contact_points_deduped,
        "suppressions_moved": suppressions_moved,
        "consents_moved": consents_moved,
        "orders_moved": orders_moved,
        "voice_calls_moved": voice_calls_moved,
        "webchat_sessions_moved": webchat_sessions_moved,
        "mappings_moved": mappings_moved,
        "preserved_aliases": preserved_aliases,
    }
