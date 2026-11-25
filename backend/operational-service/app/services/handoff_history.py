from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.system_event import SystemEvent
from app.schemas.conversation import HandoffHistoryItem, HandoffHistoryPage
from app.services.tenant_data import execute_for_tenant
from app.tenant_models.operations import Cliente, ConversacionResumen, Conversation, Lead
from app.tenant_models.whatsapp_turn import WhatsAppTurn


WHATSAPP_HANDOFF = "whatsapp.turn.handoff"
INBOUND_HANDOFF = "ingest.handoff.created"


def _reference(event: SystemEvent, field: str) -> int | None:
    value = event.payload.get(field) if isinstance(event.payload, dict) else None
    return value if type(value) is int and 1 <= value <= 9223372036854775807 else None


def list_handoff_history(db: Session, tenant: TenantContext, limit: int, before_id: int | None) -> HandoffHistoryPage:
    statement = select(SystemEvent).where(
        SystemEvent.auth_tenant_id == tenant.auth_tenant_id,
        SystemEvent.schema_name == tenant.schema_name,
        SystemEvent.event_type.in_((WHATSAPP_HANDOFF, INBOUND_HANDOFF)),
    )
    if before_id is not None:
        statement = statement.where(SystemEvent.id < before_id)
    events = db.scalars(statement.order_by(SystemEvent.id.desc()).limit(limit + 1)).all()
    page = events[:limit]
    turn_ids = {_reference(event, "turn_id") for event in page if event.event_type == WHATSAPP_HANDOFF} - {None}
    lead_ids = {_reference(event, "lead_id") for event in page if event.event_type == INBOUND_HANDOFF} - {None}

    turns = {}
    if turn_ids:
        turn_statement = select(
            WhatsAppTurn.id,
            case((ConversacionResumen.whatsapp_id.is_not(None), Conversation.id)),
            Lead.id,
            Cliente.nombre,
        ).select_from(WhatsAppTurn).join(Lead, Lead.id == WhatsAppTurn.lead_id).join(Cliente, Cliente.id == Lead.cliente_id).join(
            Conversation, Conversation.id == WhatsAppTurn.conversation_id,
        ).outerjoin(ConversacionResumen, ConversacionResumen.whatsapp_id == Conversation.session_id).where(WhatsAppTurn.id.in_(turn_ids))
        turns = {turn_id: (conversation_id, lead_id, name) for turn_id, conversation_id, lead_id, name in
                 execute_for_tenant(db, tenant.schema_name, turn_statement)}

    leads = {}
    if lead_ids:
        lead_statement = select(Lead.id, Cliente.nombre).join_from(Lead, Cliente).where(Lead.id.in_(lead_ids))
        leads = {lead_id: (None, lead_id, name) for lead_id, name in execute_for_tenant(db, tenant.schema_name, lead_statement)}

    items = []
    for event in page:
        if event.event_type == WHATSAPP_HANDOFF:
            kind = "whatsapp_turn"
            target = turns.get(_reference(event, "turn_id"))
        else:
            kind = "inbound_handoff"
            target = leads.get(_reference(event, "lead_id"))
        conversation_id, lead_id, name = target if target is not None else (None, None, None)
        items.append(HandoffHistoryItem(id=event.id, kind=kind, occurred_at=event.created_at,
                                        conversation_id=conversation_id, lead_id=lead_id, contact_name=name))

    return HandoffHistoryPage(items=items, next_before_id=page[-1].id if len(events) > limit else None)
