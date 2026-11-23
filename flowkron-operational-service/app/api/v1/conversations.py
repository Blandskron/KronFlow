from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.conversation import ConversationCursor, ConversationListResponse, ConversationOut, ConversationReadIn, ConversationReadOut, MessageListResponse
from app.services.conversation_service import get_conversation, list_conversations, list_messages, list_pending_replies, mark_conversation_read

router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])


@router.get("", response_model=ConversationListResponse)
def list_endpoint(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    channel: str | None = None,
    requires_human: bool | None = None,
    q: str | None = Query(default=None, max_length=120),
    contact_id: int | None = Query(default=None, ge=1, le=9223372036854775807),
    before_at: AwareDatetime | None = None,
    before_id: int | None = Query(default=None, gt=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    limit = min(limit, settings.max_page_size)
    if (before_at is None) != (before_id is None) or (before_at is not None and offset):
        raise HTTPException(status_code=422, detail="Provide both cursor fields without offset")
    before = (before_at, before_id) if before_at is not None and before_id is not None else None
    items, total = list_conversations(
        db, tenant, limit + 1, offset, status_filter, channel, requires_human, search=q, before=before, contact_id=contact_id,
    )
    cursor = None
    if len(items) > limit:
        tail = items[limit - 1]
        cursor = ConversationCursor(before_at=tail["last_message_at"], before_id=tail["id"])
    return ConversationListResponse(items=items[:limit], total=total, limit=limit, offset=offset, next_cursor=cursor)


@router.get("/{conversation_id}", response_model=ConversationOut)
def retrieve(conversation_id: int, tenant: TenantContext = Depends(resolve_tenant_from_jwt), db: Session = Depends(get_db)):
    conversation = get_conversation(db, tenant, conversation_id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


@router.post("/{conversation_id}/read", response_model=ConversationReadOut)
def read(
    conversation_id: int, payload: ConversationReadIn,
    tenant: TenantContext = Depends(resolve_crm_editor), db: Session = Depends(get_db),
):
    unread = mark_conversation_read(db, tenant, conversation_id, payload.through_message_id)
    if unread is None:
        raise HTTPException(status_code=404, detail="Conversation or message not found")
    return ConversationReadOut(no_leidos=unread)


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
def messages(
    conversation_id: int,
    limit: int = Query(default=100, ge=1),
    offset: int = Query(default=0, ge=0),
    order: Literal["chronological", "recent"] = "chronological",
    before_id: int | None = Query(default=None, gt=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    limit = min(limit, settings.max_page_size)
    items, total = list_messages(db, tenant, conversation_id, limit, offset, recent=order == "recent", before_id=before_id)
    pending = list_pending_replies(db, tenant, conversation_id) if order == "recent" and before_id is None and offset == 0 else []
    return MessageListResponse(items=items, total=total, limit=limit, offset=offset, pending_replies=pending)

