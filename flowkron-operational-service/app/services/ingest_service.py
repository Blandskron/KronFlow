from datetime import datetime, timezone

from sqlalchemy import select
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
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.operations import Cliente, Conversation, Ejecutivo, InventarioVehiculo, Lead, MensajeProcesado, Message, SolicitudDerecho


def _get_or_create_cliente(db: Session, phone: str, full_name: str = "", email: str = "", source: str = "whatsapp_directo") -> Cliente:
    cliente = db.scalar(select(Cliente).where(Cliente.whatsapp_id == phone))
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


def _get_or_create_lead(db: Session, cliente: Cliente) -> Lead:
    lead = db.scalar(select(Lead).where(Lead.cliente_id == cliente.id))
    if lead:
        return lead
    lead = Lead(cliente_id=cliente.id)
    db.add(lead)
    db.flush()
    return lead


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


def ingest_whatsapp_message(db: Session, tenant: TenantContext, payload: WhatsAppMessageIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    session_id = payload.external_thread_id or payload.phone
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
    lead = _get_or_create_lead(db, cliente)
    conversation = _get_or_create_conversation(db, session_id, conversation_payload)
    if _message_already_processed(db, payload.external_message_id):
        db.commit()
        return {"lead_id": lead.id, "conversation_id": conversation.id, "message_id": None, "duplicate": True}
    _mark_message_processed(db, payload.external_message_id)

    message = Message(
        whatsapp_id=session_id,
        rol="usuario" if payload.direction == "inbound" else "agente",
        mensaje=payload.body or "",
        creado_en=payload.sent_at,
    )
    db.add(message)
    create_system_event(db, "ingest.message.received", tenant.auth_tenant_id, tenant.schema_name, {"message_id": payload.external_message_id})
    db.commit()
    db.refresh(message)
    return {"lead_id": lead.id, "conversation_id": conversation.id, "message_id": message.id, "duplicate": False}


def apply_lead_classification(db: Session, tenant: TenantContext, payload: LeadClassificationIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    cliente = _get_or_create_cliente(db, payload.phone)
    lead = _get_or_create_lead(db, cliente)

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
    lead = _get_or_create_lead(db, cliente)
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
    return {
        "phone": phone,
        "consentimiento_datos": bool(cliente and cliente.consentimiento_datos),
        "fecha_consentimiento": cliente.fecha_consentimiento if cliente else None,
    }


def save_consent(db: Session, tenant: TenantContext, payload: ConsentIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    cliente = _get_or_create_cliente(db, phone=payload.phone, source="whatsapp_directo")
    cliente.telefono = payload.phone
    cliente.whatsapp_id = payload.phone
    cliente.consentimiento_datos = payload.accepted
    if payload.accepted and not cliente.fecha_consentimiento:
        cliente.fecha_consentimiento = datetime.now(timezone.utc)
    cliente.canal_consentimiento = payload.channel
    cliente.version_politica = payload.policy_version
    db.commit()
    return get_consent(db, tenant, payload.phone)


def upsert_client(db: Session, tenant: TenantContext, payload: ClientUpsertIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    cliente = db.scalar(select(Cliente).where(Cliente.rut == payload.rut))
    if not cliente:
        cliente = db.scalar(select(Cliente).where(Cliente.whatsapp_id == payload.phone))
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
    cliente.consentimiento_datos = payload.consentimiento_datos
    db.flush()
    db.commit()
    return {"id": cliente.id}


def upsert_lead(db: Session, tenant: TenantContext, payload: LeadUpsertIn) -> dict:
    bind_tenant_session(db, tenant.schema_name)
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
        messages.append(Message(whatsapp_id=payload.phone, rol="usuario", mensaje=payload.user_message))
    if payload.agent_message:
        messages.append(Message(whatsapp_id=payload.phone, rol="agente", mensaje=payload.agent_message))
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
