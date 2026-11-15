from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.tenant_resolver import TenantContext
from app.services.tenant_data import conversation_to_dict, count_for_tenant, execute_for_tenant, message_to_dict, scalar_for_tenant
from app.tenant_models.operations import Cliente, ConversacionResumen, Conversation, Lead, Message


def _filtered_conversations_statement(
    status: str | None = None,
    channel: str | None = None,
    requires_human: bool | None = None,
):
    return select(Conversation)


def _last_message(db: Session, tenant: TenantContext, conversation_id: int) -> tuple[str | None, object | None]:
    statement = (
        select(Message.mensaje, Message.creado_en)
        .join(Conversation, Conversation.session_id == Message.whatsapp_id)
        .where(Conversation.id == conversation_id)
        .order_by(Message.creado_en.desc())
        .limit(1)
    )
    row = execute_for_tenant(db, tenant.schema_name, statement).first()
    if not row:
        return None, None
    return row[0], row[1]


def _lead_for_conversation(db: Session, tenant: TenantContext, conversation: Conversation) -> Lead | None:
    payload = conversation.message or {}
    candidate_phones = [
        conversation.session_id,
        payload.get("phone"),
        payload.get("whatsapp_id"),
        payload.get("from"),
    ]
    candidate_phones = [str(phone) for phone in candidate_phones if phone]
    statement = (
        select(Lead)
        .join(Cliente, Lead.cliente_id == Cliente.id)
        .options(selectinload(Lead.cliente))
        .where(Cliente.whatsapp_id.in_(candidate_phones))
    )
    return scalar_for_tenant(db, tenant.schema_name, statement)


def _matches_filters(item: dict[str, Any], status: str | None, channel: str | None, requires_human: bool | None) -> bool:
    if status and item["status"] != status:
        return False
    if channel and item["channel"] != channel:
        return False
    if requires_human is not None and item["requires_human"] is not requires_human:
        return False
    return True


def list_conversations(
    db: Session,
    tenant: TenantContext,
    limit: int,
    offset: int,
    status: str | None = None,
    channel: str | None = None,
    requires_human: bool | None = None,
) -> tuple[list[dict[str, Any]], int]:
    statement = (
        select(ConversacionResumen, Conversation, Lead)
        .outerjoin(
            Conversation,
            Conversation.session_id == ConversacionResumen.whatsapp_id,
        )
        .outerjoin(
            Cliente,
            Cliente.whatsapp_id == ConversacionResumen.whatsapp_id,
        )
        .outerjoin(
            Lead,
            Lead.cliente_id == Cliente.id,
        )
        .options(selectinload(Lead.cliente))
        .where(Conversation.id.is_not(None))
        .distinct(ConversacionResumen.whatsapp_id)
        .order_by(
            ConversacionResumen.whatsapp_id,
            ConversacionResumen.ultimo_mensaje_en.desc(),
        )
    )

    rows = execute_for_tenant(db, tenant.schema_name, statement).all()

    items = []

    for resumen, conversation, lead in rows:
        item = conversation_to_dict(
            conversation,
            lead,
            resumen.ultimo_mensaje,
            resumen.ultimo_mensaje_en,
        )

        if _matches_filters(item, status, channel, requires_human):
            items.append(item)

    items.sort(
        key=lambda item: item.get("ultimo_mensaje_en")
        or item.get("last_message_at")
        or item.get("updated_at"),
        reverse=True,
    )

    total = len(items)

    return items[offset : offset + limit], total


def get_conversation(db: Session, tenant: TenantContext, conversation_id: int) -> dict[str, Any] | None:
    statement = (
        select(ConversacionResumen, Conversation, Lead)
        .outerjoin(Conversation, Conversation.session_id == ConversacionResumen.whatsapp_id)
        .outerjoin(Cliente, Cliente.whatsapp_id == ConversacionResumen.whatsapp_id)
        .outerjoin(Lead, Lead.cliente_id == Cliente.id)
        .options(selectinload(Lead.cliente))
        .where(Conversation.id == conversation_id)
    )
    row = execute_for_tenant(db, tenant.schema_name, statement).first()
    if not row:
        return None
    resumen, conversation, lead = row
    if not conversation:
        return None
    return conversation_to_dict(conversation, lead, resumen.ultimo_mensaje, resumen.ultimo_mensaje_en)


def list_messages(db: Session, tenant: TenantContext, conversation_id: int, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    session_id = scalar_for_tenant(db, tenant.schema_name, select(Conversation.session_id).where(Conversation.id == conversation_id))
    if not session_id:
        return [], 0
    base_statement = select(Message).where(Message.whatsapp_id == session_id)
    total = count_for_tenant(db, tenant.schema_name, base_statement)
    statement = base_statement.order_by(Message.creado_en.asc()).limit(limit).offset(offset)
    messages = execute_for_tenant(db, tenant.schema_name, statement).scalars().all()
    return [message_to_dict(message, conversation_id) for message in messages], total

