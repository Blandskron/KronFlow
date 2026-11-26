from datetime import datetime, timezone
from hashlib import sha256
import json

from fastapi import HTTPException
from sqlalchemy import func, inspect, or_, select, text, update
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.ingest import (
    ClientUpsertIn,
    ConsentIn,
    DashboardMessagesIn,
    ExecutiveAssignIn,
    ExecutiveLinkIn,
    HandoffIn,
    LeadClassificationIn,
    LeadUpsertIn,
    PrivacyRequestIn,
    WhatsAppMessageIn,
    WhatsAppStatusIn,
)
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.lead_service import get_or_create_initial_lead
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.services.workflow_cancellation import cancel_waiting_runs_in_tx
from app.tenant_models.operations import Cliente, Conversation, Ejecutivo, InventarioVehiculo, Lead, MensajeProcesado, Message, SolicitudDerecho
from app.tenant_models.whatsapp_consent import WhatsAppConsentState
from app.tenant_models.whatsapp_turn import WhatsAppTurn, WhatsAppTurnJob


TURN_JOB_CAPACITY = 128
TURN_JOB_ATTEMPT_LIMIT = 5
RECOVERABLE_TURN_STATES = ("received", "generating", "prepared")


def _lock_ingest_identity(db, schema_name, *identity):
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
               {"key": json.dumps([schema_name, *identity], separators=(",", ":"))})


def lock_turn_jobs(db: Session, tenant: TenantContext):
    _lock_ingest_identity(db, tenant.schema_name, "turn-job-admission")


def require_turn_job_capacity(db: Session):
    pending = select(WhatsAppTurnJob.turn_id).join(WhatsAppTurn).where(
        WhatsAppTurn.state.in_((*RECOVERABLE_TURN_STATES, "sending")),
        or_(WhatsAppTurnJob.attempts < TURN_JOB_ATTEMPT_LIMIT, WhatsAppTurn.lease_until > func.now()),
    ).limit(TURN_JOB_CAPACITY)
    if db.scalar(select(func.count()).select_from(pending.subquery())) >= TURN_JOB_CAPACITY:
        raise HTTPException(status_code=429, detail="WhatsApp turn queue capacity exceeded")


def _get_or_create_cliente(
    db: Session, phone: str, full_name: str = "", email: str = "", source: str = "whatsapp_directo",
    *, lock: bool = False,
) -> Cliente:
    statement = select(Cliente).where(Cliente.whatsapp_id == phone)
    cliente = db.scalar(statement.with_for_update() if lock else statement)
    if cliente:
        if full_name:
            cliente.nombre = full_name
        if email:
            cliente.email = email
        if phone:
            cliente.telefono = phone
        return cliente

    cliente = Cliente(
        rut=f"wa:{phone}",
        nombre=full_name or phone,
        email=email or None,
        telefono=phone,
        whatsapp_id=phone,
        canal_origen=source,
    )
    db.add(cliente)
    db.flush()
    return cliente


def _get_or_create_conversation(db: Session, session_id: str, payload: dict) -> Conversation:
    conversation = db.scalar(select(Conversation).where(Conversation.session_id == session_id))
    if conversation:
        conversation.message = payload
        return conversation
    conversation = Conversation(session_id=session_id, message=payload)
    db.add(conversation)
    db.flush()
    return conversation


def _mark_message_processed(db: Session, external_message_id: str) -> MensajeProcesado:
    processed = db.scalar(select(MensajeProcesado).where(MensajeProcesado.message_id == external_message_id))
    if processed:
        return processed
    processed = MensajeProcesado(message_id=external_message_id)
    db.add(processed)
    db.flush()
    return processed


def _message_already_processed(db: Session, external_message_id: str) -> bool:
    return db.scalar(select(MensajeProcesado.id).where(MensajeProcesado.message_id == external_message_id)) is not None


def ingest_whatsapp_message(
    db: Session, tenant: TenantContext, payload: WhatsAppMessageIn, *,
    create_turn: bool = False, job: WhatsAppTurnJob | None = None,
) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    session_id = payload.external_thread_id or payload.phone
    if job is not None:
        create_turn = True
        lock_turn_jobs(db, tenant)
    # Lock before any read/upsert. The unique index is the final invariant;
    # locks also prevent races creating contacts, leads and conversations.
    # Scope comes from the authenticated tenant, never from request schema input.
    for identity in (
        [payload.connection_id, payload.channel, "message", payload.external_message_id],
        ["phone", payload.phone],
        ["thread", session_id],
    ):
        _lock_ingest_identity(db, tenant.schema_name, *identity)

    existing = db.scalar(select(Message).where(
        Message.connection_id == payload.connection_id,
        Message.channel == payload.channel,
        Message.external_message_id == payload.external_message_id,
    ))
    if existing and (existing.whatsapp_id != session_id or existing.direction != payload.direction):
        raise HTTPException(status_code=409, detail="Message identity belongs to another thread or direction")
    if existing or _message_already_processed(db, payload.external_message_id):
        # Old markers have no reliable link to historical message rows. Retain
        # their deduplication behavior without guessing a message ID or mutating
        # the contact/conversation when receiving a duplicate.
        lead_id = db.scalar(select(Lead.id).join(Cliente).where(Cliente.whatsapp_id == payload.phone))
        conversation_id = db.scalar(select(Conversation.id).where(Conversation.session_id == session_id))
        message_id = existing.id if existing else None
        db.commit()
        return {"lead_id": lead_id, "conversation_id": conversation_id,
                "message_id": message_id, "duplicate": True}
    if create_turn:
        recipient = db.scalar(select(Cliente).where(Cliente.whatsapp_id == payload.phone))
        if recipient is None or not recipient.consentimiento_datos:
            raise HTTPException(status_code=403, detail="WhatsApp consent is required")
        if job is not None and ordered_consent_ready(db, tenant):
            decision = db.get(WhatsAppConsentState, recipient.id)
            if decision and decision.authorized_from and payload.sent_at < decision.authorized_from:
                raise HTTPException(status_code=403, detail="Message predates the current WhatsApp consent")
    if job is not None:
        require_turn_job_capacity(db)
    raw_payload = payload.raw_payload or {}
    conversation_payload = {
        **payload.model_dump(mode="json"),
        "raw_payload": raw_payload,
        **raw_payload,
    }

    cliente = _get_or_create_cliente(
        db,
        phone=payload.phone,
        full_name=payload.full_name,
        email=payload.email,
        source=payload.channel,
    )
    lead, _ = get_or_create_initial_lead(db, cliente.id)
    conversation = _get_or_create_conversation(db, session_id, conversation_payload)
    _mark_message_processed(db, payload.external_message_id)

    message = Message(
        whatsapp_id=session_id,
        rol="usuario" if payload.direction == "inbound" else "agente",
        mensaje=payload.body or "",
        creado_en=payload.sent_at,
        connection_id=payload.connection_id,
        channel=payload.channel,
        external_message_id=payload.external_message_id,
        provider_message_id=payload.provider_message_id,
        direction=payload.direction,
        message_type=payload.message_type,
        delivery_status=payload.delivery_status or ("received" if payload.direction == "inbound" else "unknown"),
    )
    db.add(message)
    if create_turn:
        db.flush()
        db.add(WhatsAppTurn(id=message.id, phone=payload.phone, lead_id=lead.id, conversation_id=conversation.id))
        if job is not None:
            db.flush()
            job.turn_id = message.id
            db.add(job)
    create_system_event(db, "ingest.message.received", tenant.auth_tenant_id, tenant.schema_name, {"message_id": payload.external_message_id})
    if payload.direction == "inbound":
        publish_domain_event_in_tx(
            db,
            tenant,
            event_type="message.inbound.received",
            aggregate_type="conversation",
            aggregate_id=conversation.id,
            payload={
                "conversation_id": conversation.id,
                "contact_id": cliente.id,
                "lead_id": lead.id,
                "message_id": payload.external_message_id,
                "channel": payload.channel,
            },
            occurred_at=payload.sent_at,
        )
        cancel_waiting_runs_in_tx(
            db,
            tenant,
            event_type="message.inbound.received",
            contact_id=cliente.id,
            conversation_id=conversation.id,
            reason="customer_replied",
            now=payload.sent_at,
        )
    db.commit()
    db.refresh(message)
    return {"lead_id": lead.id, "conversation_id": conversation.id, "message_id": message.id, "duplicate": False}


def apply_lead_classification(db: Session, tenant: TenantContext, payload: LeadClassificationIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    cliente = _get_or_create_cliente(db, payload.phone)
    lead, _ = get_or_create_initial_lead(db, cliente.id)

    if payload.temperature is not None:
        lead.clasificacion = {"cold": "frio", "warm": "tibio", "hot": "caliente"}.get(payload.temperature, payload.temperature)
    if payload.lifecycle_status is not None:
        lead.estado = payload.lifecycle_status
    if payload.score is not None:
        lead.score_lead = payload.score
    if payload.metadata:
        lead.resumen_ia = payload.metadata.get("summary") or payload.metadata.get("resumen_ia") or lead.resumen_ia

    create_system_event(db, "ingest.lead.classified", tenant.auth_tenant_id, tenant.schema_name, {"lead_id": lead.id})
    db.commit()
    return {"lead_id": lead.id}


def create_handoff(db: Session, tenant: TenantContext, payload: HandoffIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    cliente = _get_or_create_cliente(db, payload.phone)
    lead, _ = get_or_create_initial_lead(db, cliente.id)
    lead.estado = "en_proceso"
    lead.estado_seguimiento = "requiere_humano"
    create_system_event(db, "ingest.handoff.created", tenant.auth_tenant_id, tenant.schema_name, {"lead_id": lead.id})
    db.commit()
    return {"lead_id": lead.id, "conversation_id": None, "message_id": None}


def update_whatsapp_status(db: Session, tenant: TenantContext, payload: WhatsAppStatusIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    conversation = db.scalar(select(Conversation).where(Conversation.session_id == payload.external_thread_id))
    if conversation:
        conversation.message = {**(conversation.message or {}), "status": payload.status}
    db.commit()
    return {"conversation_id": conversation.id if conversation else None}


def inventory_for_agent(db: Session, tenant: TenantContext, limit: int = 50) -> list[dict]:
    bind_tenant_session(db, tenant.schema_name)
    items = db.scalars(
        select(InventarioVehiculo)
        .where(InventarioVehiculo.disponible.is_(True))
        .order_by(InventarioVehiculo.marca.asc(), InventarioVehiculo.modelo.asc(), InventarioVehiculo.anio.desc())
        .limit(limit)
    ).all()
    return [
        {
            "marca": item.marca,
            "modelo": item.modelo,
            "anio": item.anio,
            "version": item.version,
            "color": item.color,
            "condicion": item.condicion,
            "kilometraje": item.kilometraje,
            "tipo_vehiculo": item.tipo_vehiculo,
            "transmision": item.transmision,
            "combustible": item.combustible,
            "precio_lista": item.precio_lista,
        }
        for item in items
    ]


def get_customer_by_phone(db: Session, tenant: TenantContext, phone: str) -> dict | None:
    bind_tenant_session(db, tenant.schema_name)
    cliente = db.scalar(select(Cliente).where(Cliente.whatsapp_id == phone, Cliente.nombre.not_in(["pendiente", "ANONIMIZADO"])))
    if not cliente:
        return None
    return {
        "id": cliente.id,
        "rut": cliente.rut,
        "nombre": cliente.nombre,
        "email": cliente.email,
        "telefono": cliente.telefono,
        "whatsapp_id": cliente.whatsapp_id,
    }


def get_consent(db: Session, tenant: TenantContext, phone: str) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    cliente = db.scalar(select(Cliente).where(Cliente.whatsapp_id == phone))
    return _consent_snapshot(phone, cliente)


def _consent_snapshot(phone: str, cliente: Cliente | None) -> dict:
    return {
        "phone": phone,
        "consentimiento_datos": bool(cliente and cliente.consentimiento_datos),
        "fecha_consentimiento": cliente.fecha_consentimiento if cliente else None,
    }


def save_consent(db: Session, tenant: TenantContext, payload: ConsentIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    _lock_ingest_identity(db, tenant.schema_name, "phone", payload.phone)
    marker = None
    if payload.external_message_id is not None:
        identity = json.dumps([payload.phone, payload.external_message_id], separators=(",", ":"))
        marker = f"flowkron:consent:{sha256(identity.encode()).hexdigest()}"
        if _message_already_processed(db, marker):
            result = get_consent(db, tenant, payload.phone)
            db.commit()
            return {**result, "duplicate": True}
    cliente = _get_or_create_cliente(db, phone=payload.phone, source="whatsapp_directo", lock=True)
    applied = _apply_consent(
        db, tenant, cliente, payload.accepted,
        provider_at=payload.sent_at, channel=payload.channel, policy_version=payload.policy_version,
    )
    if marker is not None:
        _mark_message_processed(db, marker)
    result = _consent_snapshot(payload.phone, cliente)
    db.commit()
    return result | {"stale": not applied}


def ordered_consent_ready(db: Session, tenant: TenantContext) -> bool:
    return inspect(db.connection()).has_table(WhatsAppConsentState.__tablename__, schema=tenant.schema_name)


def _cancel_consent_turns(
    db: Session, tenant: TenantContext, cliente: Cliente, now: datetime, *, before: datetime | None = None,
) -> None:
    if not inspect(db.connection()).has_table(WhatsAppTurn.__tablename__, schema=tenant.schema_name):
        return
    # A granted send keeps its state and can still be acknowledged or reconciled.
    statement = update(WhatsAppTurn).where(
        or_(WhatsAppTurn.phone == cliente.whatsapp_id,
            WhatsAppTurn.lead_id.in_(select(Lead.id).where(Lead.cliente_id == cliente.id))),
        WhatsAppTurn.state.in_(RECOVERABLE_TURN_STATES),
    )
    reason = "consent_withdrawn"
    if before is not None:
        statement = statement.where(select(Message.id).where(
            Message.id == WhatsAppTurn.id, Message.creado_en < before,
        ).exists())
        reason = "consent_superseded_by_renewal"
    db.execute(statement.values(state="cancelled", lease_until=None, last_error=reason, updated_at=now))


def _apply_consent(
    db: Session, tenant: TenantContext, cliente: Cliente, accepted: bool, *,
    provider_at: datetime | None = None, channel: str | None = None, policy_version: str | None = None,
) -> bool:
    now = datetime.now(timezone.utc)
    effective_at = min(provider_at.replace(microsecond=0), now.replace(microsecond=0)) if provider_at else now
    if ordered_consent_ready(db, tenant):
        decision = db.get(WhatsAppConsentState, cliente.id)
        if decision is not None and provider_at is not None:
            # WhatsApp timestamps have second resolution. A withdrawal wins an
            # ambiguous tie, regardless of which delivery reached us first.
            if effective_at < decision.decision_at or (
                effective_at == decision.decision_at and (accepted or not cliente.consentimiento_datos)
            ):
                # A late withdrawal inside the open consent period does not
                # overturn a later grant. It closes the preceding period.
                if not accepted and cliente.consentimiento_datos and (
                    decision.authorized_from is None or effective_at >= decision.authorized_from
                ):
                    decision.authorized_from = decision.decision_at
                    _cancel_consent_turns(db, tenant, cliente, now, before=decision.authorized_from)
                    create_system_event(db, "whatsapp.consent.prior_withdrawal", tenant.auth_tenant_id, tenant.schema_name, {
                        "client_id": cliente.id,
                        "decision_at": effective_at.isoformat(),
                        "authorized_from": decision.authorized_from.isoformat(),
                    })
                return False
        if decision is None:
            decision = WhatsAppConsentState(client_id=cliente.id, decision_at=effective_at)
            db.add(decision)
        decision.decision_at = max(effective_at, decision.decision_at)
        if not accepted:
            decision.authorized_from = None
        elif not cliente.consentimiento_datos:
            decision.authorized_from = effective_at if provider_at is not None else None
    elif provider_at is not None:
        raise HTTPException(status_code=503, detail="WhatsApp consent schema is unavailable")

    changed = cliente.consentimiento_datos != accepted
    cliente.consentimiento_datos = accepted
    if channel is not None:
        cliente.canal_consentimiento = channel
        cliente.telefono = cliente.whatsapp_id
    if policy_version is not None:
        cliente.version_politica = policy_version
    if accepted and (changed or cliente.fecha_consentimiento is None):
        cliente.fecha_consentimiento = now
    if not accepted:
        _cancel_consent_turns(db, tenant, cliente, now)
    if changed or provider_at is not None:
        create_system_event(db, "whatsapp.consent.changed", tenant.auth_tenant_id, tenant.schema_name, {
            "client_id": cliente.id, "accepted": accepted,
            "channel": cliente.canal_consentimiento, "policy_version": cliente.version_politica,
            "decision_at": effective_at.isoformat(), "source": "whatsapp_message" if provider_at else "operational",
        })
    return True


def upsert_client(db: Session, tenant: TenantContext, payload: ClientUpsertIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    _lock_ingest_identity(db, tenant.schema_name, "phone", payload.phone)
    cliente = db.scalar(select(Cliente).where(Cliente.rut == payload.rut).with_for_update())
    if not cliente:
        cliente = db.scalar(select(Cliente).where(Cliente.whatsapp_id == payload.phone).with_for_update())
    creating = cliente is None
    if not cliente:
        cliente = Cliente(rut=payload.rut, nombre=payload.nombre, canal_origen="whatsapp_directo")
        db.add(cliente)
    cliente.rut = payload.rut
    cliente.nombre = payload.nombre
    cliente.email = payload.email
    cliente.telefono = payload.phone
    cliente.whatsapp_id = payload.phone
    cliente.tipo_cliente = "prospecto"
    cliente.canal_origen = "whatsapp_directo"
    db.flush()
    if creating or "consentimiento_datos" in payload.model_fields_set:
        _apply_consent(db, tenant, cliente, payload.consentimiento_datos)
    db.commit()
    return {"id": cliente.id}


def upsert_lead(db: Session, tenant: TenantContext, payload: LeadUpsertIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    if db.scalar(select(Cliente.id).where(Cliente.id == payload.cliente_id).with_for_update()) is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    lead = db.scalar(select(Lead).where(Lead.cliente_id == payload.cliente_id).order_by(Lead.creado_en.desc()))
    if not lead:
        lead = Lead(cliente_id=payload.cliente_id)
        db.add(lead)
    lead.score_lead = payload.score
    lead.clasificacion = payload.clasificacion
    lead.plazo_compra = payload.plazo_compra
    lead.requiere_credito = payload.requiere_credito
    lead.estado = payload.estado
    lead.resumen_ia = payload.resumen_ia
    lead.estado_seguimiento = payload.estado_seguimiento
    db.flush()
    create_system_event(db, "ingest.lead.upserted", tenant.auth_tenant_id, tenant.schema_name, {"lead_id": lead.id})
    db.commit()
    return {"id": lead.id, "cliente_id": lead.cliente_id}


def register_privacy_request(db: Session, tenant: TenantContext, payload: PrivacyRequestIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    request = SolicitudDerecho(whatsapp_id=payload.phone, tipo_derecho=payload.tipo_derecho, estado="pendiente")
    db.add(request)
    db.flush()
    create_system_event(db, "ingest.privacy_request.created", tenant.auth_tenant_id, tenant.schema_name, {"request_id": request.id})
    db.commit()
    return {"id": request.id}


def register_dashboard_messages(db: Session, tenant: TenantContext, payload: DashboardMessagesIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    messages: list[Message] = []
    if payload.user_message:
        messages.append(Message(whatsapp_id=payload.phone, rol="usuario", direction="inbound", mensaje=payload.user_message))
    if payload.agent_message:
        messages.append(Message(whatsapp_id=payload.phone, rol="agente", direction="outbound", mensaje=payload.agent_message))
    db.add_all(messages)
    db.flush()
    ids = [message.id for message in messages]
    db.commit()
    return {"message_ids": ids}


def assign_executive(db: Session, tenant: TenantContext, payload: ExecutiveAssignIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    executive = db.scalar(
        select(Ejecutivo)
        .where(Ejecutivo.activo.is_(True))
        .order_by(Ejecutivo.leads_asignados.asc(), Ejecutivo.id.asc())
        .limit(1)
    )
    if not executive:
        return {}
    executive.leads_asignados = (executive.leads_asignados or 0) + 1
    executive.ultimo_asignado_at = datetime.now(timezone.utc)
    lead = db.get(Lead, payload.lead_id)
    if lead:
        lead.ejecutivo_id = executive.id
    db.commit()
    return {"id": executive.id, "nombre": executive.nombre, "whatsapp": executive.whatsapp, "leads_asignados": executive.leads_asignados}


def link_executive(db: Session, tenant: TenantContext, payload: ExecutiveLinkIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    lead = db.get(Lead, payload.lead_id)
    executive = db.get(Ejecutivo, payload.executive_id)
    if lead and executive:
        lead.ejecutivo_id = executive.id
        db.commit()
        return {"id": executive.id, "nombre": executive.nombre, "whatsapp": executive.whatsapp, "leads_asignados": executive.leads_asignados}
    db.commit()
    return {}
