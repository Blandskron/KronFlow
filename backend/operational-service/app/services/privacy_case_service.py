from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import delete, func, inspect, or_, select, update
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.privacy_case import CaseState, PrivacyCaseTransition
from app.services.consent_authorization_service import record_suppression
from app.services.post_v1_service import _resolve_attachment_path
from app.services.tenant_data import bind_tenant_session, count_for_tenant, execute_for_tenant
from app.services.tenant_provisioning_service import create_system_event
from app.services.workflow_cancellation import cancel_waiting_runs_in_tx
from app.tenant_models.ai_extensions import ConversationMemoryItem
from app.tenant_models.consent_ledger import ContactConsentDecision, ContactSuppression
from app.tenant_models.contact_capture import ContactPoint
from app.tenant_models.operations import Cliente, Conversation, Lead, LogLimpieza, Message, SolicitudDerecho
from app.tenant_models.opportunity import Opportunity
from app.tenant_models.phase4_hub import WebchatSession
from app.tenant_models.phase5_integrations import ExternalEntityMapping
from app.tenant_models.post_v1 import PrivateAttachment
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


def export_privacy_case_data(db: Session, tenant: TenantContext, case_id: int, *, actor_id: str) -> dict:
    """Export all tenant-scoped CRM, messaging, and consent records for a privacy case subject (FK-27)."""
    now = datetime.now(UTC)
    bind_tenant_session(db, tenant.schema_name)
    case_row = db.get(SolicitudDerecho, case_id)
    if case_row is None:
        raise HTTPException(status_code=404, detail="Privacy case not found")

    existing_tables = set(inspect(db.connection()).get_table_names(schema=tenant.schema_name))
    subject = db.scalar(select(Cliente).where(Cliente.whatsapp_id == case_row.whatsapp_id))
    subject_dict = None
    contact_points = []
    leads = []
    opportunities = []
    decisions = []
    suppressions = []
    memory_items = []
    attachments = []
    webchat_sessions_count = 0
    external_mappings_count = 0
    workflow_runs_count = 0

    if subject is not None:
        subject_dict = {
            "id": subject.id,
            "nombre": subject.nombre,
            "email": subject.email,
            "telefono": subject.telefono,
            "whatsapp_id": subject.whatsapp_id,
            "consentimiento_datos": subject.consentimiento_datos,
            "creado_en": subject.creado_en.isoformat() if subject.creado_en else None,
        }
        if ContactPoint.__tablename__ in existing_tables:
            contact_points = [
                {"id": p.id, "point_type": p.point_type, "normalized_value": p.normalized_value, "verified": p.verified}
                for p in db.scalars(select(ContactPoint).where(ContactPoint.client_id == subject.id)).all()
            ]
        leads = [
            {"id": l.id, "estado": l.estado, "clasificacion": l.clasificacion}
            for l in db.scalars(select(Lead).where(Lead.cliente_id == subject.id)).all()
        ]
        if Opportunity.__tablename__ in existing_tables:
            opportunities = [
                {"id": o.id, "title": o.title, "outcome": o.outcome, "currency": o.currency}
                for o in db.scalars(select(Opportunity).where(Opportunity.contact_id == subject.id)).all()
            ]
        if ContactConsentDecision.__tablename__ in existing_tables:
            decisions = [
                {
                    "id": d.id,
                    "channel": d.channel,
                    "destination": d.destination,
                    "purpose": d.purpose,
                    "granted": d.granted,
                    "effective_at": d.effective_at.isoformat(),
                }
                for d in db.scalars(select(ContactConsentDecision).where(ContactConsentDecision.client_id == subject.id)).all()
            ]
        if ContactSuppression.__tablename__ in existing_tables:
            suppressions = [
                {"id": s.id, "channel": s.channel, "destination": s.destination, "purpose": s.purpose, "reason": s.reason}
                for s in db.scalars(select(ContactSuppression).where(ContactSuppression.client_id == subject.id)).all()
            ]

        conv_ids = set(db.scalars(select(Conversation.id).where(Conversation.session_id == case_row.whatsapp_id)).all())
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

    message_count = int(
        db.scalar(select(func.count()).select_from(Message).where(Message.whatsapp_id == case_row.whatsapp_id)) or 0
    )
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
        "consent_decisions": decisions,
        "suppressions": suppressions,
        "memory_items": memory_items,
        "attachments": attachments,
        "webchat_sessions_count": webchat_sessions_count,
        "external_mappings_count": external_mappings_count,
        "workflow_runs_count": workflow_runs_count,
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

    points_deleted = 0
    for client in clients:
        client.nombre = "Anonimizado"
        client.email = None
        client.telefono = None
        client.whatsapp_id = f"anon:{client.id}"
        client.consentimiento_datos = False
        if ContactPoint.__tablename__ in existing_tables:
            res_pt = db.execute(delete(ContactPoint).where(ContactPoint.client_id == client.id))
            points_deleted += int(res_pt.rowcount or 0)

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

    memory_items_deleted = 0
    if ConversationMemoryItem.__tablename__ in existing_tables and conv_ids:
        mem_res = db.execute(delete(ConversationMemoryItem).where(ConversationMemoryItem.conversation_id.in_(conv_ids)))
        memory_items_deleted = int(mem_res.rowcount or 0)

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
        update(Message).where(Message.whatsapp_id == original_wa).values(mensaje="[REDACTED_PRIVACY]")
    )
    messages_redacted = int(msg_res.rowcount or 0)

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
    if ContactSuppression.__tablename__ in existing_tables and original_wa and not original_wa.startswith("anon:"):
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

    case_row.estado = "completada"
    case_row.fecha_resolucion = now

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

