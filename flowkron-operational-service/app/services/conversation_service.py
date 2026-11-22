from datetime import datetime
from typing import Any

from sqlalchemy import case, func, or_, select, tuple_, update
from sqlalchemy.orm import Session, joinedload

from app.core.tenant_resolver import TenantContext
from app.services.ingest_service import RECOVERABLE_TURN_STATES, TURN_JOB_ATTEMPT_LIMIT
from app.services.tenant_data import STATUS_TO_API, conversation_to_dict, count_for_tenant, execute_for_tenant, message_to_dict, scalar_for_tenant
from app.services.whatsapp_turn_service import turn_jobs_ready, turn_receipts_ready
from app.tenant_models.operations import Cliente, ConversacionResumen, Conversation, Lead, Message
from app.tenant_models.whatsapp_turn import WhatsAppSendEvidence, WhatsAppTurn, WhatsAppTurnJob


def _conversation_rows():
    latest_leads = (
        select(Cliente.whatsapp_id, Lead.id.label("lead_id")).select_from(Lead)
        .join_from(Lead, Cliente, Lead.cliente_id == Cliente.id)
        .where(Cliente.whatsapp_id.is_not(None))
        .distinct(Cliente.whatsapp_id).order_by(Cliente.whatsapp_id, Lead.id.desc()).subquery()
    )
    return (
        select(ConversacionResumen, Conversation, Lead)
        .select_from(ConversacionResumen)
        .join_from(ConversacionResumen, Conversation, Conversation.session_id == ConversacionResumen.whatsapp_id)
        .outerjoin_from(ConversacionResumen, latest_leads, latest_leads.c.whatsapp_id == ConversacionResumen.whatsapp_id)
        .outerjoin_from(latest_leads, Lead, Lead.id == latest_leads.c.lead_id)
    )


def _to_item(summary, conversation, lead):
    item = conversation_to_dict(conversation, lead, summary.ultimo_mensaje, summary.ultimo_mensaje_en)
    item["no_leidos"] = summary.no_leidos
    return item


def _inbox_threads():
    first_conversations = (
        select(Conversation.session_id, func.min(Conversation.id).label("conversation_id"))
        .group_by(Conversation.session_id).subquery()
    )
    return _conversation_rows().join_from(Conversation, first_conversations, first_conversations.c.conversation_id == Conversation.id)


def _inbox_state():
    raw_status = func.lower(func.btrim(Conversation.message["status"].astext))
    human = func.coalesce(Lead.estado_seguimiento == "requiere_humano", False) | func.coalesce(
        raw_status.in_(("waiting", "requires_human", "requiere_humano")), False
    )
    effective_status = case(
        (human, "waiting"),
        (raw_status.in_(("new", "active", "closed")), raw_status),
        else_=case(STATUS_TO_API, value=Lead.estado, else_="active"),
    )
    return effective_status, human


def inbox_counts_statement():
    status, human = _inbox_state()
    threads = _inbox_threads().with_only_columns(
        Conversation.id, status.label("status"), human.label("requires_human"),
    ).subquery()
    return select(
        func.count().filter(threads.c.status != "closed").label("open_conversations"),
        func.count().filter(threads.c.requires_human).label("requires_human"),
    )


def list_conversations(
    db: Session,
    tenant: TenantContext,
    limit: int,
    offset: int,
    status: str | None = None,
    channel: str | None = None,
    requires_human: bool | None = None,
    *,
    search: str | None = None,
    before: tuple[datetime, int] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    statement = _inbox_threads()
    effective_status, human = _inbox_state()
    if status:
        statement = statement.where(effective_status == status)
    if channel:
        statement = statement.where(func.coalesce(
            func.nullif(Conversation.message["channel"].astext, ""),
            func.nullif(Conversation.message["source"].astext, ""), "whatsapp",
        ) == channel)
    if requires_human is not None:
        statement = statement.where(human.is_(requires_human))
    if search and (search := search.strip()):
        statement = statement.outerjoin_from(Lead, Cliente, Cliente.id == Lead.cliente_id).where(or_(
            ConversacionResumen.whatsapp_id.icontains(search, autoescape=True),
            Cliente.nombre.icontains(search, autoescape=True),
            Cliente.telefono.icontains(search, autoescape=True),
            ConversacionResumen.ultimo_mensaje.icontains(search, autoescape=True),
        ))
    matching = statement.with_only_columns(
        Conversation.id.label("conversation_id"),
        ConversacionResumen.whatsapp_id.label("summary_id"),
        ConversacionResumen.ultimo_mensaje_en.label("activity_at"),
        Lead.id.label("lead_id"),
        func.count().over().label("total"),
    ).subquery()
    page = select(matching)
    if before is not None:
        page = page.where(tuple_(matching.c.activity_at, matching.c.conversation_id) < before)
    page = page.order_by(matching.c.activity_at.desc(), matching.c.conversation_id.desc()).offset(offset).limit(limit).subquery()
    result = (
        select(ConversacionResumen, Conversation, Lead, page.c.total).select_from(page)
        .join_from(page, ConversacionResumen, ConversacionResumen.whatsapp_id == page.c.summary_id)
        .join_from(page, Conversation, Conversation.id == page.c.conversation_id)
        .outerjoin_from(page, Lead, Lead.id == page.c.lead_id)
        .options(joinedload(Lead.cliente))
        .order_by(page.c.activity_at.desc(), page.c.conversation_id.desc())
    )
    rows = execute_for_tenant(db, tenant.schema_name, result).all()
    if rows:
        return [_to_item(summary, conversation, lead) for summary, conversation, lead, _ in rows], rows[0].total
    if offset or before is not None:
        return [], count_for_tenant(db, tenant.schema_name, statement.with_only_columns(Conversation.id))
    return [], 0


def get_conversation(db: Session, tenant: TenantContext, conversation_id: int) -> dict[str, Any] | None:
    statement = _conversation_rows().options(joinedload(Lead.cliente)).where(Conversation.id == conversation_id)
    row = execute_for_tenant(db, tenant.schema_name, statement).first()
    if not row:
        return None
    return _to_item(*row)


def mark_conversation_read(db: Session, tenant: TenantContext, conversation_id: int, through_message_id: int) -> int | None:
    summary_id = scalar_for_tenant(db, tenant.schema_name, select(ConversacionResumen.whatsapp_id).join(
        Conversation, Conversation.session_id == ConversacionResumen.whatsapp_id,
    ).where(Conversation.id == conversation_id).with_for_update(of=ConversacionResumen))
    if summary_id is None:
        return None
    thread_filter = Message.whatsapp_id == summary_id
    if scalar_for_tenant(db, tenant.schema_name, select(Message.id).where(thread_filter, Message.id == through_message_id)) is None:
        return None
    unseen = select(func.count()).select_from(Message).where(
        thread_filter, Message.id > through_message_id, Message.rol == "usuario",
    ).scalar_subquery()
    unread = scalar_for_tenant(db, tenant.schema_name, update(ConversacionResumen).where(
        ConversacionResumen.whatsapp_id == summary_id,
    ).values(no_leidos=func.least(ConversacionResumen.no_leidos, unseen)).returning(ConversacionResumen.no_leidos))
    db.commit()
    return unread


def list_messages(
    db: Session, tenant: TenantContext, conversation_id: int, limit: int, offset: int,
    *, recent: bool = False, before_id: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    session_id = scalar_for_tenant(db, tenant.schema_name, select(Conversation.session_id).where(Conversation.id == conversation_id))
    if not session_id:
        return [], 0
    base_statement = select(Message).where(Message.whatsapp_id == session_id)
    if before_id is not None:
        base_statement = base_statement.where(Message.id < before_id)
    total = count_for_tenant(db, tenant.schema_name, base_statement)
    # The inbox follows the order in which turns were saved. WhatsApp and the
    # server can stamp the same turn with different clocks.
    ordering = (Message.id.desc(),) if recent else (Message.creado_en.asc(), Message.id.asc())
    statement = base_statement.order_by(*ordering).limit(limit).offset(offset)
    messages = execute_for_tenant(db, tenant.schema_name, statement).scalars().all()
    failed = [message.id for message in messages if message.direction == "outbound" and message.delivery_status == "failed"]
    reasons = {}
    if failed and turn_receipts_ready(db, tenant):
        evidence = select(WhatsAppTurn.outbound_message_id, WhatsAppSendEvidence.failure_reason).join(
            WhatsAppSendEvidence, WhatsAppSendEvidence.turn_id == WhatsAppTurn.id,
        ).where(WhatsAppTurn.outbound_message_id.in_(failed))
        reasons = dict(execute_for_tenant(db, tenant.schema_name, evidence).tuples().all())
    return [
        message_to_dict(message, conversation_id) | {"delivery_failure_reason": reasons.get(message.id)}
        for message in messages
    ], total


def list_pending_replies(db: Session, tenant: TenantContext, conversation_id: int) -> list[dict]:
    if not turn_jobs_ready(db, tenant):
        return []
    status = case(
        (WhatsAppTurn.state == "unknown", "unknown"),
        ((WhatsAppTurn.state == "sending") & (WhatsAppTurn.lease_until <= func.now()), "unknown"),
        (WhatsAppTurn.state == "sending", "sending"),
        ((WhatsAppTurnJob.attempts >= TURN_JOB_ATTEMPT_LIMIT) & or_(
            WhatsAppTurn.lease_until.is_(None), WhatsAppTurn.lease_until <= func.now(),
        ), "not_sent"),
        else_="queued",
    )
    statement = select(WhatsAppTurn.id.label("inbound_message_id"), status.label("status")).join_from(
        WhatsAppTurn, WhatsAppTurnJob, WhatsAppTurnJob.turn_id == WhatsAppTurn.id,
    ).join_from(WhatsAppTurn, Conversation, Conversation.id == WhatsAppTurn.conversation_id).where(
        Conversation.session_id == select(Conversation.session_id).where(
            Conversation.id == conversation_id,
        ).correlate(None).scalar_subquery(),
        WhatsAppTurn.state.in_((*RECOVERABLE_TURN_STATES, "sending", "unknown")),
    ).order_by(WhatsAppTurn.id.desc()).limit(50)
    return [dict(row) for row in execute_for_tenant(db, tenant.schema_name, statement).mappings()]

