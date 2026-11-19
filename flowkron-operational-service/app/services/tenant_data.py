from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.tenant_models.operations import Lead


TEMPERATURE_TO_API = {"frio": "cold", "tibio": "warm", "caliente": "hot"}
STATUS_TO_API = {
    "nuevo": "new",
    "contactado": "active",
    "en_proceso": "active",
    "ganado": "closed",
    "perdido": "closed",
}


def tenant_exec_options(schema_name: str) -> dict[str, Any]:
    return {"schema_translate_map": {"tenant": schema_name}}


def bind_tenant_session(db: Session, schema_name: str) -> None:
    options = tenant_exec_options(schema_name)
    if db.bind:
        db.bind = db.bind.execution_options(**options)
    try:
        conn = db.connection()
        conn._execution_options = conn._execution_options.union(options)
    except Exception:
        pass


def execute_for_tenant(db: Session, schema_name: str, statement):
    return db.execute(statement, execution_options=tenant_exec_options(schema_name))


def scalar_for_tenant(db: Session, schema_name: str, statement):
    return db.scalar(statement, execution_options=tenant_exec_options(schema_name))


def count_for_tenant(db: Session, schema_name: str, statement: Select) -> int:
    count_statement = select(func.count()).select_from(statement.subquery())
    return int(scalar_for_tenant(db, schema_name, count_statement) or 0)


def lead_to_dict(lead: Lead) -> dict[str, Any]:
    cliente = lead.cliente
    metadata = {
        "rut": cliente.rut if cliente else "",
        "tipo_cliente": cliente.tipo_cliente if cliente else "prospecto",
        "plazo_compra": lead.plazo_compra,
        "requiere_credito": lead.requiere_credito,
        "resumen_ia": lead.resumen_ia,
        "followup_count": lead.followup_count,
        "ultimo_followup_at": lead.ultimo_followup_at,
        "estado_seguimiento": lead.estado_seguimiento,
    }
    return {
        "id": lead.id,
        "cliente_id": lead.cliente_id,
        "rut": cliente.rut if cliente else "",
        "nombre": cliente.nombre if cliente else "",
        "email": (cliente.email or "") if cliente else "",
        "telefono": cliente.telefono if cliente else "",
        "whatsapp_id": cliente.whatsapp_id if cliente else "",
        "tipo_cliente": cliente.tipo_cliente if cliente else "prospecto",
        "score_lead": lead.score_lead,
        "clasificacion": lead.clasificacion,
        "plazo_compra": lead.plazo_compra,
        "requiere_credito": lead.requiere_credito,
        "estado": lead.estado,
        "resumen_ia": lead.resumen_ia,
        "followup_count": lead.followup_count,
        "ultimo_followup_at": lead.ultimo_followup_at,
        "estado_seguimiento": lead.estado_seguimiento,
        "ejecutivo_id": lead.ejecutivo_id,
        "creado_en": lead.creado_en,
        "actualizado_en": lead.actualizado_en,
        "full_name": cliente.nombre if cliente else "",
        "phone": cliente.telefono or cliente.whatsapp_id if cliente else "",
        "source": cliente.canal_origen if cliente else "whatsapp_directo",
        "direction": "inbound",
        "temperature": TEMPERATURE_TO_API.get(lead.clasificacion, "cold"),
        "lifecycle_status": lead.estado,
        "assigned_to_user_id": lead.ejecutivo_id,
        "score": lead.score_lead,
        "tags": [],
        "metadata": metadata,
        "created_at": lead.creado_en,
        "updated_at": lead.actualizado_en,
    }


def conversation_to_dict(
    conversation,
    lead: Lead | None = None,
    last_message: str | None = None,
    last_message_at=None,
) -> dict[str, Any]:
    payload = conversation.message or {}
    cliente = lead.cliente if lead else None
    status = _conversation_status(payload, lead)
    requires_human = bool(lead and lead.estado_seguimiento == "requiere_humano") or status == "waiting"
    channel = payload.get("channel") or payload.get("source") or "whatsapp"
    return {
        "id": conversation.id,
        "session_id": conversation.session_id,
        "message": conversation.message,
        "creado_en": conversation.creado_en,
        "lead_id": lead.id if lead else 0,
        "lead_name": cliente.nombre if cliente else conversation.session_id,
        "lead_phone": cliente.telefono or cliente.whatsapp_id if cliente else conversation.session_id,
        "channel": channel,
        "external_thread_id": conversation.session_id,
        "status": "waiting" if requires_human else status,
        "requires_human": requires_human,
        "last_message_at": last_message_at or conversation.creado_en,
        "last_message": last_message,
        "temperature": TEMPERATURE_TO_API.get(lead.clasificacion) if lead else None,
        "created_at": conversation.creado_en,
        "updated_at": last_message_at or conversation.creado_en,
    }


def message_to_dict(message, conversation_id: int | None = None) -> dict[str, Any]:
    return {
        "id": message.id,
        "conversation_id": conversation_id or 0,
        # Preserve the historical API fallback without fabricating provider IDs.
        "external_message_id": message.external_message_id or str(message.id),
        "connection_id": message.connection_id,
        "channel": message.channel,
        "provider_message_id": message.provider_message_id,
        "direction": message.direction,
        "message_type": message.message_type,
        "delivery_status": message.delivery_status,
        "recorded_at": message.recorded_at,
        "sender_type": "lead" if message.rol == "usuario" else "agent",
        "body": message.mensaje,
        "raw_payload": {},
        "sent_at": message.creado_en,
        "created_at": message.creado_en,
        "whatsapp_id": message.whatsapp_id,
        "rol": message.rol,
        "mensaje": message.mensaje,
        "creado_en": message.creado_en,
    }


def agent_to_dict(agent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "status": agent.status,
        "prompt_config": agent.prompt_config,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }


def _conversation_status(payload: dict[str, Any], lead: Lead | None = None) -> str:
    raw_status = str(payload.get("status") or "").lower()
    if raw_status in {"new", "active", "waiting", "closed"}:
        return raw_status
    if raw_status in {"requires_human", "requiere_humano"}:
        return "waiting"
    if lead:
        return STATUS_TO_API.get(lead.estado, "active")
    return "active"
