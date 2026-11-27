from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import delete, func, inspect, or_, select, update
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.privacy_case import CaseState, PrivacyCaseCreateIn, PrivacyCaseTransition
from app.services.consent_authorization_service import build_ts27560_consent_receipt, record_suppression
from app.services.post_v1_service import _resolve_attachment_path
from app.services.tenant_data import bind_tenant_session, count_for_tenant, execute_for_tenant
from app.services.tenant_provisioning_service import create_system_event
from app.services.workflow_cancellation import cancel_waiting_runs_in_tx
from app.tenant_models.agent_platform import AgentExecutionTrace
from app.tenant_models.ai_extensions import ContactEnrichmentCandidate, ConversationMemoryItem
from app.tenant_models.ai_proposal import AIActionProposal
from app.tenant_models.consent_ledger import ContactConsentDecision, ContactSuppression
from app.tenant_models.contact_capture import ContactPoint
from app.tenant_models.domain_events import DomainEvent
from app.tenant_models.operations import (
    Cliente,
    ConversacionResumen,
    Conversation,
    Lead,
    LogLimpieza,
    Message,
    RateLimit,
    SolicitudDerecho,
)
from app.tenant_models.opportunity import Opportunity, OpportunityActivity
from app.tenant_models.phase4_hub import WebchatSession
from app.tenant_models.phase5_integrations import ExternalEntityMapping
from app.tenant_models.phase6_extensions import CommerceOrder, VoiceCallSegment, VoiceCallSession
from app.tenant_models.post_v1 import PrivateAttachment
from app.tenant_models.whatsapp_turn import WhatsAppTurn
from app.tenant_models.workflows import WorkflowRun


CASE_FIELDS = (
    SolicitudDerecho.id, SolicitudDerecho.tipo_derecho.label("kind"), SolicitudDerecho.estado.label("state"),
    SolicitudDerecho.fecha_solicitud.label("requested_at"), SolicitudDerecho.fecha_limite.label("due_at"),
    SolicitudDerecho.fecha_resolucion.label("completed_at"),
)
NEXT_STATE = {"pendiente": "en_proceso", "en_proceso": "completada"}


def list_privacy_cases(db: Session, tenant: TenantContext, state: CaseState | None, limit: int, offset: int) -> dict:
    statement = select(*CASE_FIELDS)
    if state is not None:
        statement = statement.where(SolicitudDerecho.estado == state)
    total = count_for_tenant(db, tenant.schema_name, statement)
    page = statement.order_by(SolicitudDerecho.fecha_limite, SolicitudDerecho.id).limit(limit).offset(offset)
    items = execute_for_tenant(db, tenant.schema_name, page).mappings().all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def transition_privacy_case(
    db: Session, tenant: TenantContext, case_id: int, transition: PrivacyCaseTransition, actor_id: str,
):
    if NEXT_STATE[transition.expected_state] != transition.state:
        raise HTTPException(status_code=422, detail="Invalid privacy case transition")
    closing = transition.state == "completada"
    if closing and not transition.confirmed:
        raise HTTPException(status_code=422, detail="Confirm the request was handled before closing")

    target = SolicitudDerecho.id == case_id
    current = execute_for_tenant(db, tenant.schema_name, select(*CASE_FIELDS).where(target).with_for_update()).mappings().one_or_none()
    if current is None:
        raise HTTPException(status_code=404, detail="Privacy case not found")
    if current["state"] == transition.state:
        return current
    if current["state"] != transition.expected_state:
        raise HTTPException(status_code=409, detail="Privacy case state changed since it was loaded")

    statement = update(SolicitudDerecho).where(target).values(
        estado=transition.state, fecha_resolucion=func.now() if closing else None,
    ).returning(*CASE_FIELDS)
    result = execute_for_tenant(db, tenant.schema_name, statement).mappings().one()
    create_system_event(db, "privacy.case.state.changed", tenant.auth_tenant_id, tenant.schema_name, {
        "case_id": case_id, "previous_state": transition.expected_state, "state": transition.state, "actor_id": actor_id,
    })
    db.commit()
    return result


def _resolve_case_subject(db: Session, case_row: SolicitudDerecho) -> Cliente | None:
    if getattr(case_row, "client_id", None):
        found = db.get(Cliente, case_row.client_id)
        if found is not None:
            return found
    if getattr(case_row, "subject_email", None):
        found = db.scalar(select(Cliente).where(func.lower(Cliente.email) == case_row.subject_email.strip().lower()))
        if found is not None:
            return found
    if case_row.whatsapp_id and not case_row.whatsapp_id.startswith(("anon:", "contact:", "email:")):
        return db.scalar(select(Cliente).where(Cliente.whatsapp_id == case_row.whatsapp_id))
    return None


def create_privacy_case(
    db: Session, tenant: TenantContext, payload: PrivacyCaseCreateIn, *, actor_id: str,
) -> dict:
    """Create a multichannel DSAR case by contact_id, email, or whatsapp_id (PRV-013)."""
    if not any([payload.contact_id, payload.email, payload.whatsapp_id]):
        raise HTTPException(status_code=422, detail="Provide at least one of contact_id, email, or whatsapp_id")
    bind_tenant_session(db, tenant.schema_name)
    subject = None
    if payload.contact_id is not None:
        subject = db.get(Cliente, payload.contact_id)
        if subject is None:
            raise HTTPException(status_code=404, detail="Contact not found")
    elif payload.email:
        subject = db.scalar(select(Cliente).where(func.lower(Cliente.email) == payload.email.strip().lower()))
    elif payload.whatsapp_id:
        subject = db.scalar(select(Cliente).where(Cliente.whatsapp_id == payload.whatsapp_id.strip()))

    wa_ref = (
        (payload.whatsapp_id or "").strip()
        or (subject.whatsapp_id if subject and subject.whatsapp_id else "")
        or (f"contact:{subject.id}" if subject else f"email:{(payload.email or '').strip().lower()}")
    )
    row = SolicitudDerecho(
        client_id=subject.id if subject else payload.contact_id,
        subject_email=(payload.email or (subject.email if subject else None)),
        whatsapp_id=wa_ref,
        tipo_derecho=payload.kind,
        estado="pendiente",
        notas=payload.notas.strip()[:1000] if payload.notas else None,
    )
    db.add(row)
    db.flush()
    create_system_event(
        db,
        "privacy.case.created",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"case_id": row.id, "kind": row.tipo_derecho, "client_id": row.client_id, "actor_id": actor_id},
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "kind": row.tipo_derecho,
        "state": row.estado,
        "requested_at": row.fecha_solicitud,
        "due_at": row.fecha_limite,
        "completed_at": row.fecha_resolucion,
    }


def export_privacy_case_data(db: Session, tenant: TenantContext, case_id: int, *, actor_id: str) -> dict:
    """Export full portable tenant-scoped CRM, messaging, voice, commerce, and consent records (PRV-013)."""
    now = datetime.now(UTC)
    bind_tenant_session(db, tenant.schema_name)
    case_row = db.get(SolicitudDerecho, case_id)
    if case_row is None:
        raise HTTPException(status_code=404, detail="Privacy case not found")

    existing_tables = set(inspect(db.connection()).get_table_names(schema=tenant.schema_name))
    subject = _resolve_case_subject(db, case_row)
    subject_dict = None
    contact_points = []
    leads = []
    opportunities = []
    decisions = []
    consent_receipts = []
    suppressions = []
    memory_items = []
    attachments = []
    voice_transcripts = []
    commerce_orders = []
    webchat_sessions_count = 0
    external_mappings_count = 0
    workflow_runs_count = 0
    voice_calls_count = 0
    commerce_orders_count = 0

    if subject is not None:
        subject_dict = {
            "id": subject.id,
            "nombre": subject.nombre,
            "email": subject.email,
            "telefono": subject.telefono,
            "whatsapp_id": subject.whatsapp_id,
            "consentimiento_datos": subject.consentimiento_datos,
            "processing_restricted": bool(getattr(subject, "processing_restricted", False)),
            "creado_en": subject.creado_en.isoformat() if subject.creado_en else None,
        }
        if ContactPoint.__tablename__ in existing_tables:
            contact_points = [
                {"id": p.id, "point_type": p.point_type, "normalized_value": p.normalized_value, "verified": p.verified}
                for p in db.scalars(select(ContactPoint).where(ContactPoint.client_id == subject.id)).all()
            ]
        leads = [
            {
                "id": l.id,
                "estado": l.estado,
                "clasificacion": l.clasificacion,
                "score_lead": l.score_lead,
                "score_factors": dict(getattr(l, "score_factors_json", None) or {}),
                "human_review_requested": bool(getattr(l, "human_review_requested", False)),
            }
            for l in db.scalars(select(Lead).where(Lead.cliente_id == subject.id)).all()
        ]
        if Opportunity.__tablename__ in existing_tables:
            opportunities = [
                {"id": o.id, "title": o.title, "outcome": o.outcome, "currency": o.currency}
                for o in db.scalars(select(Opportunity).where(Opportunity.contact_id == subject.id)).all()
            ]
        if ContactConsentDecision.__tablename__ in existing_tables:
            decision_rows = list(
                db.scalars(select(ContactConsentDecision).where(ContactConsentDecision.client_id == subject.id)).all()
            )
            decisions = [
                {
                    "id": d.id,
                    "channel": d.channel,
                    "destination": d.destination,
                    "purpose": d.purpose,
                    "granted": d.granted,
                    "legal_basis": getattr(d, "legal_basis", "consent"),
                    "effective_at": d.effective_at.isoformat(),
                }
                for d in decision_rows
            ]
            consent_receipts = [
                build_ts27560_consent_receipt(d, tenant_slug=tenant.tenant_slug)
                for d in decision_rows
            ]
        if ContactSuppression.__tablename__ in existing_tables:
            suppressions = [
                {"id": s.id, "channel": s.channel, "destination": s.destination, "purpose": s.purpose, "reason": s.reason}
                for s in db.scalars(select(ContactSuppression).where(ContactSuppression.client_id == subject.id)).all()
            ]

        wa_lookup = subject.whatsapp_id or case_row.whatsapp_id
        conv_ids = set(db.scalars(select(Conversation.id).where(Conversation.session_id == wa_lookup)).all()) if wa_lookup else set()
        if WebchatSession.__tablename__ in existing_tables:
            wc_conv_ids = list(
                db.scalars(select(WebchatSession.conversation_id).where(WebchatSession.client_id == subject.id)).all()
            )
            webchat_sessions_count = len(wc_conv_ids)
            conv_ids.update(wc_conv_ids)
        if ConversationMemoryItem.__tablename__ in existing_tables and conv_ids:
            memory_items = [
                {
                    "id": m.id,
                    "conversation_id": m.conversation_id,
                    "memory_key": m.memory_key,
                    "memory_value": m.memory_value,
                    "source_type": m.source_type,
                }
                for m in db.scalars(
                    select(ConversationMemoryItem).where(ConversationMemoryItem.conversation_id.in_(conv_ids))
                ).all()
            ]
        if PrivateAttachment.__tablename__ in existing_tables:
            att_filters = [
                (PrivateAttachment.resource_type == "contact") & (PrivateAttachment.resource_id == subject.id)
            ]
            if conv_ids:
                att_filters.append(
                    (PrivateAttachment.resource_type == "conversation") & (PrivateAttachment.resource_id.in_(conv_ids))
                )
            attachments = [
                {"id": a.id, "resource_type": a.resource_type, "filename": a.filename, "size_bytes": a.size_bytes}
                for a in db.scalars(
                    select(PrivateAttachment).where(PrivateAttachment.deleted_at.is_(None), or_(*att_filters))
                ).all()
            ]
        if ExternalEntityMapping.__tablename__ in existing_tables:
            external_mappings_count = int(
                db.scalar(
                    select(func.count())
                    .select_from(ExternalEntityMapping)
                    .where(ExternalEntityMapping.local_type == "contact", ExternalEntityMapping.local_id == str(subject.id))
                )
                or 0
            )
        if WorkflowRun.__tablename__ in existing_tables:
            workflow_runs_count = int(
                db.scalar(
                    select(func.count()).select_from(WorkflowRun).where(WorkflowRun.contact_id == subject.id)
                )
                or 0
            )
        if VoiceCallSession.__tablename__ in existing_tables:
            call_rows = list(
                db.scalars(select(VoiceCallSession).where(VoiceCallSession.client_id == subject.id)).all()
            )
            voice_calls_count = len(call_rows)
            if call_rows and VoiceCallSegment.__tablename__ in existing_tables:
                call_ids = [c.id for c in call_rows]
                voice_transcripts = [
                    {
                        "call_id": seg.call_id,
                        "speaker": seg.speaker,
                        "transcript": seg.transcript,
                        "created_at": seg.created_at.isoformat() if seg.created_at else None,
                    }
                    for seg in db.scalars(
                        select(VoiceCallSegment)
                        .where(VoiceCallSegment.call_id.in_(call_ids))
                        .order_by(VoiceCallSegment.call_id.asc(), VoiceCallSegment.sequence_no.asc())
                    ).all()
                ]
        if CommerceOrder.__tablename__ in existing_tables:
            order_rows = list(
                db.scalars(select(CommerceOrder).where(CommerceOrder.client_id == subject.id)).all()
            )
            commerce_orders_count = len(order_rows)
            commerce_orders = [
                {
                    "id": o.id,
                    "order_number": o.order_number,
                    "status": o.status,
                    "currency": o.currency,
                    "expected_amount_minor": o.expected_amount_minor,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                }
                for o in order_rows
            ]

    msg_wa = (subject.whatsapp_id if subject and subject.whatsapp_id else case_row.whatsapp_id) or ""
    msg_rows = (
        list(
            db.scalars(
                select(Message).where(Message.whatsapp_id == msg_wa).order_by(Message.creado_en.asc(), Message.id.asc())
            ).all()
        )
        if msg_wa
        else []
    )
    messages_list = [
        {
            "id": m.id,
            "channel": m.channel,
            "direction": m.direction,
            "rol": m.rol,
            "mensaje": m.mensaje,
            "creado_en": m.creado_en.isoformat() if m.creado_en else None,
        }
        for m in msg_rows
    ]
    message_count = len(messages_list)
    create_system_event(
        db,
        "privacy.case.exported",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {
            "case_id": case_id,
            "actor_id": actor_id,
            "message_count": message_count,
            "lead_count": len(leads),
            "memory_count": len(memory_items),
            "attachment_count": len(attachments),
        },
    )
    db.commit()
    return {
        "case_id": case_id,
        "kind": case_row.tipo_derecho,
        "exported_at": now,
        "subject_contact": subject_dict,
        "contact_points": contact_points,
        "leads": leads,
        "opportunities": opportunities,
        "message_count": message_count,
        "messages": messages_list,
        "consent_decisions": decisions,
        "consent_receipts": consent_receipts,
        "suppressions": suppressions,
        "memory_items": memory_items,
        "attachments": attachments,
        "voice_transcripts": voice_transcripts,
        "commerce_orders": commerce_orders,
        "webchat_sessions_count": webchat_sessions_count,
        "external_mappings_count": external_mappings_count,
        "workflow_runs_count": workflow_runs_count,
        "voice_calls_count": voice_calls_count,
        "commerce_orders_count": commerce_orders_count,
    }


def rectify_privacy_case_subject(
    db: Session,
    tenant: TenantContext,
    case_id: int,
    *,
    nombre: str | None = None,
    email: str | None = None,
    telefono: str | None = None,
    actor_id: str,
) -> dict:
    """Exercise GDPR Art. 16 / Ley 21.719 Art. 6 right of rectification (PRV-014)."""
    now = datetime.now(UTC)
    bind_tenant_session(db, tenant.schema_name)
    case_row = db.scalar(select(SolicitudDerecho).where(SolicitudDerecho.id == case_id).with_for_update())
    if case_row is None:
        raise HTTPException(status_code=404, detail="Privacy case not found")
    subject = _resolve_case_subject(db, case_row)
    if subject is None:
        raise HTTPException(status_code=404, detail="Privacy case subject not found")

    changed: list[str] = []
    if nombre is not None and nombre.strip():
        subject.nombre = nombre.strip()[:180]
        changed.append("nombre")
    if email is not None:
        subject.email = email.strip().lower() or None
        changed.append("email")
    if telefono is not None:
        subject.telefono = telefono.strip() or None
        changed.append("telefono")
    if not changed:
        raise HTTPException(status_code=422, detail="Provide at least one field to rectify")

    case_row.estado = "completada"
    case_row.fecha_resolucion = now
    create_system_event(
        db,
        "privacy.case.rectified",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"case_id": case_id, "client_id": subject.id, "fields": changed, "actor_id": actor_id},
    )
    db.commit()
    return {
        "case_id": case_id,
        "client_id": subject.id,
        "state": case_row.estado,
        "rectified_fields": changed,
    }


def set_privacy_case_restriction(
    db: Session,
    tenant: TenantContext,
    case_id: int,
    *,
    restricted: bool,
    reason: str | None,
    actor_id: str,
) -> dict:
    """Exercise GDPR Art. 18 / Ley 21.719 Art. 8 ter processing restriction / temporary block (PRV-014)."""
    now = datetime.now(UTC)
    bind_tenant_session(db, tenant.schema_name)
    case_row = db.scalar(select(SolicitudDerecho).where(SolicitudDerecho.id == case_id).with_for_update())
    if case_row is None:
        raise HTTPException(status_code=404, detail="Privacy case not found")
    subject = _resolve_case_subject(db, case_row)
    if subject is None:
        raise HTTPException(status_code=404, detail="Privacy case subject not found")

    subject.processing_restricted = bool(restricted)
    subject.processing_restricted_reason = (reason.strip()[:240] if reason else None) if restricted else None

    cancelled_runs = 0
    if restricted:
        cancelled_runs = cancel_waiting_runs_in_tx(
            db,
            tenant,
            event_type="contact.suppressed",
            contact_id=subject.id,
            reason="processing_restricted",
            now=now,
        )

    create_system_event(
        db,
        "privacy.processing.restricted",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {
            "case_id": case_id,
            "client_id": subject.id,
            "restricted": bool(restricted),
            "reason": subject.processing_restricted_reason,
            "workflow_runs_cancelled": cancelled_runs,
            "actor_id": actor_id,
        },
    )
    db.commit()
    return {
        "case_id": case_id,
        "client_id": subject.id,
        "processing_restricted": bool(subject.processing_restricted),
        "reason": subject.processing_restricted_reason,
        "workflow_runs_cancelled": cancelled_runs,
    }


def execute_privacy_erasure(
    db: Session,
    tenant: TenantContext,
    case_id: int,
    *,
    actor_id: str,
    confirmed: bool,
    storage_dir: str | Path | None = None,
) -> dict:
    """Atomically anonymize subject PII, redact messages, delete memory/attachments/sessions, and suppress re-contact."""
    if not confirmed:
        raise HTTPException(status_code=422, detail="Explicit confirmation is required to execute erasure")
    now = datetime.now(UTC)
    bind_tenant_session(db, tenant.schema_name)

    case_row = db.scalar(select(SolicitudDerecho).where(SolicitudDerecho.id == case_id).with_for_update())
    if case_row is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Privacy case not found")

    original_wa = case_row.whatsapp_id
    existing_tables = set(inspect(db.connection()).get_table_names(schema=tenant.schema_name))

    clients = list(db.scalars(select(Cliente).where(Cliente.whatsapp_id == original_wa).with_for_update()).all())
    client_ids = [c.id for c in clients]
    conv_ids = set(db.scalars(select(Conversation.id).where(Conversation.session_id == original_wa)).all())
    anon_wa = f"anon:{clients[0].id}" if clients else f"anon:case-{case_id}"

    # Capture email destinations BEFORE anonymizing client.email or deleting contact_points (PRV-003).
    original_emails: set[str] = {
        c.email.strip().lower() for c in clients if c.email and c.email.strip()
    }
    if ContactPoint.__tablename__ in existing_tables and client_ids:
        for ep in db.scalars(
            select(ContactPoint.normalized_value).where(
                ContactPoint.client_id.in_(client_ids),
                ContactPoint.point_type == "email",
            )
        ).all():
            if ep and ep.strip():
                original_emails.add(ep.strip().lower())

    points_deleted = 0
    for client in clients:
        rut_digest = hashlib.sha256(f"{tenant.schema_name}:{client.id}:{client.rut}".encode("utf-8")).hexdigest()[:16]
        client.rut = f"anon-{rut_digest}"
        client.rut_encrypted = None
        client.rut_blind_index = None
        client.nombre = "Anonimizado"
        client.email = None
        client.telefono = None
        client.whatsapp_id = f"anon:{client.id}"
        client.consentimiento_datos = False
        if ContactPoint.__tablename__ in existing_tables:
            res_pt = db.execute(delete(ContactPoint).where(ContactPoint.client_id == client.id))
            points_deleted += int(res_pt.rowcount or 0)

    if ContactEnrichmentCandidate.__tablename__ in existing_tables and client_ids:
        db.execute(delete(ContactEnrichmentCandidate).where(ContactEnrichmentCandidate.client_id.in_(client_ids)))

    webchat_sessions_anonymized = 0
    if WebchatSession.__tablename__ in existing_tables and client_ids:
        wc_conv_ids = list(
            db.scalars(select(WebchatSession.conversation_id).where(WebchatSession.client_id.in_(client_ids))).all()
        )
        conv_ids.update(wc_conv_ids)
        wc_res = db.execute(
            update(WebchatSession)
            .where(WebchatSession.client_id.in_(client_ids))
            .values(visitor_name="Anonimizado", visitor_email=None, status="closed")
        )
        webchat_sessions_anonymized = int(wc_res.rowcount or 0)

    conversations_redacted = 0
    if conv_ids:
        conv_res = db.execute(
            update(Conversation)
            .where(Conversation.id.in_(conv_ids))
            .values(session_id=anon_wa, message={"redacted": True, "reason": "privacy_erasure"})
        )
        conversations_redacted = int(conv_res.rowcount or 0)

    if ConversacionResumen.__tablename__ in existing_tables and original_wa:
        db.execute(delete(ConversacionResumen).where(ConversacionResumen.whatsapp_id == original_wa))

    if RateLimit.__tablename__ in existing_tables and original_wa:
        db.execute(delete(RateLimit).where(RateLimit.whatsapp_id == original_wa))

    lead_ids: list[int] = []
    leads_redacted = 0
    if client_ids:
        lead_ids = list(db.scalars(select(Lead.id).where(Lead.cliente_id.in_(client_ids))).all())
        if lead_ids:
            lead_res = db.execute(
                update(Lead)
                .where(Lead.id.in_(lead_ids))
                .values(resumen_ia="[REDACTED_PRIVACY]", requiere_credito=False)
            )
            leads_redacted = int(lead_res.rowcount or 0)

    opp_ids: list[int] = []
    activities_redacted = 0
    if Opportunity.__tablename__ in existing_tables and client_ids:
        opp_ids = list(db.scalars(select(Opportunity.id).where(Opportunity.contact_id.in_(client_ids))).all())
        if opp_ids and OpportunityActivity.__tablename__ in existing_tables:
            act_res = db.execute(
                update(OpportunityActivity)
                .where(OpportunityActivity.opportunity_id.in_(opp_ids))
                .values(note="[REDACTED_PRIVACY]", metadata_json={"redacted": True})
            )
            activities_redacted = int(act_res.rowcount or 0)

    proposals_redacted = 0
    if AIActionProposal.__tablename__ in existing_tables:
        prop_filters = []
        if client_ids:
            prop_filters.append((AIActionProposal.resource_type == "contact") & (AIActionProposal.resource_id.in_(client_ids)))
        if lead_ids:
            prop_filters.append((AIActionProposal.resource_type == "lead") & (AIActionProposal.resource_id.in_(lead_ids)))
        if opp_ids:
            prop_filters.append((AIActionProposal.resource_type == "opportunity") & (AIActionProposal.resource_id.in_(opp_ids)))
        if conv_ids:
            prop_filters.append((AIActionProposal.resource_type == "conversation") & (AIActionProposal.resource_id.in_(conv_ids)))
        if prop_filters:
            prop_res = db.execute(
                update(AIActionProposal)
                .where(or_(*prop_filters))
                .values(
                    arguments_json={"redacted": True},
                    rationale="[REDACTED_PRIVACY]",
                    review_note="[REDACTED_PRIVACY]",
                    effect_result={"redacted": True},
                )
            )
            proposals_redacted = int(prop_res.rowcount or 0)

    domain_events_redacted = 0
    if DomainEvent.__tablename__ in existing_tables:
        ev_filters = []
        if client_ids:
            ev_filters.append((DomainEvent.aggregate_type == "contact") & (DomainEvent.aggregate_id.in_([str(i) for i in client_ids])))
        if lead_ids:
            ev_filters.append((DomainEvent.aggregate_type == "lead") & (DomainEvent.aggregate_id.in_([str(i) for i in lead_ids])))
        if opp_ids:
            ev_filters.append((DomainEvent.aggregate_type == "opportunity") & (DomainEvent.aggregate_id.in_([str(i) for i in opp_ids])))
        if conv_ids:
            ev_filters.append((DomainEvent.aggregate_type == "conversation") & (DomainEvent.aggregate_id.in_([str(i) for i in conv_ids])))
        if ev_filters:
            ev_res = db.execute(
                update(DomainEvent)
                .where(or_(*ev_filters))
                .values(payload={"redacted": True, "reason": "privacy_erasure"})
            )
            domain_events_redacted = int(ev_res.rowcount or 0)

    external_mappings_deleted = 0
    if ExternalEntityMapping.__tablename__ in existing_tables and client_ids:
        map_res = db.execute(
            delete(ExternalEntityMapping).where(
                ExternalEntityMapping.local_type == "contact",
                ExternalEntityMapping.local_id.in_([str(i) for i in client_ids]),
            )
        )
        external_mappings_deleted = int(map_res.rowcount or 0)

    memory_items_deleted = 0
    if ConversationMemoryItem.__tablename__ in existing_tables and conv_ids:
        mem_res = db.execute(delete(ConversationMemoryItem).where(ConversationMemoryItem.conversation_id.in_(conv_ids)))
        memory_items_deleted = int(mem_res.rowcount or 0)

    if AgentExecutionTrace.__tablename__ in existing_tables and (conv_ids or original_wa):
        trace_refs = [str(i) for i in conv_ids]
        if original_wa:
            trace_refs.append(original_wa)
        db.execute(
            update(AgentExecutionTrace)
            .where(AgentExecutionTrace.conversation_id.in_(trace_refs))
            .values(query="[REDACTED_PRIVACY]", output_message="[REDACTED_PRIVACY]")
        )

    if WhatsAppTurn.__tablename__ in existing_tables and (conv_ids or original_wa):
        turn_filters = []
        if conv_ids:
            turn_filters.append(WhatsAppTurn.conversation_id.in_(conv_ids))
        if original_wa:
            turn_filters.append(WhatsAppTurn.phone == original_wa)
        db.execute(
            update(WhatsAppTurn)
            .where(or_(*turn_filters))
            .values(phone=anon_wa, reply_body="[REDACTED_PRIVACY]")
        )

    attachments_deleted = 0
    attachment_keys_to_unlink: list[str] = []
    if PrivateAttachment.__tablename__ in existing_tables and (client_ids or conv_ids):
        att_filters = []
        if client_ids:
            att_filters.append((PrivateAttachment.resource_type == "contact") & (PrivateAttachment.resource_id.in_(client_ids)))
        if conv_ids:
            att_filters.append((PrivateAttachment.resource_type == "conversation") & (PrivateAttachment.resource_id.in_(conv_ids)))
        attachment_keys_to_unlink = list(
            db.scalars(select(PrivateAttachment.storage_key).where(or_(*att_filters))).all()
        )
        att_res = db.execute(delete(PrivateAttachment).where(or_(*att_filters)))
        attachments_deleted = int(att_res.rowcount or 0)

    msg_res = db.execute(
        update(Message)
        .where(Message.whatsapp_id == original_wa)
        .values(mensaje="[REDACTED_PRIVACY]", whatsapp_id=anon_wa)
    )
    messages_redacted = int(msg_res.rowcount or 0)

    voice_segments_redacted = 0
    if (
        VoiceCallSession.__tablename__ in existing_tables
        and VoiceCallSegment.__tablename__ in existing_tables
        and (client_ids or conv_ids)
    ):
        vc_filters = []
        if client_ids:
            vc_filters.append(VoiceCallSession.client_id.in_(client_ids))
        if conv_ids:
            vc_filters.append(VoiceCallSession.conversation_id.in_(conv_ids))
        call_ids = list(db.scalars(select(VoiceCallSession.id).where(or_(*vc_filters))).all())
        if call_ids:
            db.execute(
                update(VoiceCallSession)
                .where(VoiceCallSession.id.in_(call_ids))
                .values(from_number="[REDACTED]", to_number="[REDACTED]")
            )
            seg_res = db.execute(
                update(VoiceCallSegment)
                .where(VoiceCallSegment.call_id.in_(call_ids))
                .values(transcript="[REDACTED_PRIVACY]")
            )
            voice_segments_redacted = int(seg_res.rowcount or 0)

    workflow_runs_cancelled = 0
    for cid in client_ids:
        workflow_runs_cancelled += cancel_waiting_runs_in_tx(
            db,
            tenant,
            event_type="contact.suppressed",
            contact_id=cid,
            reason="privacy_erasure",
            now=now,
        )

    suppression_recorded = False
    email_suppressions_recorded = 0
    if ContactSuppression.__tablename__ in existing_tables:
        if original_wa and not original_wa.startswith("anon:"):
            record_suppression(
                db,
                tenant,
                channel="whatsapp",
                destination=original_wa,
                purpose=None,
                reason="baja",
                source="operational",
                client_id=clients[0].id if clients else None,
                actor_id=actor_id,
                recorded_at=now,
                commit=False,
            )
            suppression_recorded = True
        for email_dest in sorted(original_emails):
            record_suppression(
                db,
                tenant,
                channel="email",
                destination=email_dest,
                purpose=None,
                reason="baja",
                source="operational",
                client_id=clients[0].id if clients else None,
                actor_id=actor_id,
                recorded_at=now,
                commit=False,
            )
            email_suppressions_recorded += 1
            suppression_recorded = True

    case_row.estado = "completada"
    case_row.fecha_resolucion = now
    case_row.whatsapp_id = anon_wa
    case_row.subject_email = None
    if case_row.notas:
        case_row.notas = "[REDACTED_PRIVACY]"

    cleanup = LogLimpieza(
        fecha_ejecucion=now,
        mensajes_eliminados=messages_redacted,
        clientes_anonimizados=len(clients),
        solicitudes_eliminadas=1,
        estado="exitoso",
        detalle={
            "case_id": case_id,
            "actor_id": actor_id,
            "contact_points_deleted": points_deleted,
            "memory_items_deleted": memory_items_deleted,
            "attachments_deleted": attachments_deleted,
            "webchat_sessions_anonymized": webchat_sessions_anonymized,
            "workflow_runs_cancelled": workflow_runs_cancelled,
            "voice_segments_redacted": voice_segments_redacted,
            "email_suppressions_recorded": email_suppressions_recorded,
            "conversations_redacted": conversations_redacted,
            "leads_redacted": leads_redacted,
            "activities_redacted": activities_redacted,
            "proposals_redacted": proposals_redacted,
            "domain_events_redacted": domain_events_redacted,
            "external_mappings_deleted": external_mappings_deleted,
        },
        notas=f"Ejecucion de borrado/anonimizacion caso #{case_id}",
    )
    db.add(cleanup)
    db.flush()
    create_system_event(
        db,
        "privacy.case.erased",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {
            "case_id": case_id,
            "actor_id": actor_id,
            "clients_anonymized": len(clients),
            "messages_redacted": messages_redacted,
            "attachments_deleted": attachments_deleted,
            "memory_items_deleted": memory_items_deleted,
            "email_suppressions_recorded": email_suppressions_recorded,
            "cleanup_log_id": cleanup.id,
        },
    )
    db.commit()
    for key in attachment_keys_to_unlink:
        try:
            _resolve_attachment_path(key, storage_dir=storage_dir).unlink(missing_ok=True)
        except HTTPException:
            pass
    return {
        "case_id": case_id,
        "state": case_row.estado,
        "clients_anonymized": len(clients),
        "messages_redacted": messages_redacted,
        "contact_points_deleted": points_deleted,
        "suppression_recorded": suppression_recorded,
        "cleanup_log_id": cleanup.id,
        "memory_items_deleted": memory_items_deleted,
        "attachments_deleted": attachments_deleted,
        "webchat_sessions_anonymized": webchat_sessions_anonymized,
        "workflow_runs_cancelled": workflow_runs_cancelled,
        "voice_segments_redacted": voice_segments_redacted,
        "email_suppressions_recorded": email_suppressions_recorded,
        "conversations_redacted": conversations_redacted,
        "leads_redacted": leads_redacted,
        "activities_redacted": activities_redacted,
        "proposals_redacted": proposals_redacted,
        "domain_events_redacted": domain_events_redacted,
        "external_mappings_deleted": external_mappings_deleted,
    }


def run_retention_sweep(
    db: Session,
    tenant: TenantContext,
    *,
    message_retention_days: int,
    actor_id: str,
    now: datetime | None = None,
) -> dict:
    """Purge messages older than tenant retention window and record LogLimpieza audit (FK-27)."""
    if message_retention_days < 1 or message_retention_days > 3650:
        raise HTTPException(status_code=422, detail="message_retention_days must be between 1 and 3650")
    current = now.astimezone(UTC) if now is not None else datetime.now(UTC)
    cutoff = current - timedelta(days=message_retention_days)

    bind_tenant_session(db, tenant.schema_name)
    del_res = db.execute(delete(Message).where(Message.creado_en < cutoff))
    deleted = int(del_res.rowcount or 0)

    cleanup = LogLimpieza(
        fecha_ejecucion=current,
        mensajes_eliminados=deleted,
        clientes_anonimizados=0,
        solicitudes_eliminadas=0,
        estado="exitoso",
        detalle={"retention_days": message_retention_days, "cutoff": cutoff.isoformat(), "actor_id": actor_id},
        notas="Barrido de retencion de mensajes",
    )
    db.add(cleanup)
    db.flush()
    create_system_event(
        db,
        "privacy.retention.swept",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"retention_days": message_retention_days, "messages_deleted": deleted, "cleanup_log_id": cleanup.id},
    )
    db.commit()
    return {
        "message_retention_days": message_retention_days,
        "messages_deleted": deleted,
        "cleanup_log_id": cleanup.id,
        "swept_at": current,
    }

