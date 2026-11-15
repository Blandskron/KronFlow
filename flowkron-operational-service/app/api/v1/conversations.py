from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.tenant_resolver import TenantContext, resolve_tenant_from_jwt
from app.schemas.conversation import ConversationListResponse, ConversationOut, MessageListResponse
from app.services.conversation_service import get_conversation, list_conversations, list_messages

router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])


@router.get("", response_model=ConversationListResponse)
def list_endpoint(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    channel: str | None = None,
    requires_human: bool | None = None,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    limit = min(limit, settings.max_page_size)
    items, total = list_conversations(db, tenant, limit, offset, status_filter, channel, requires_human)
    return ConversationListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{conversation_id}", response_model=ConversationOut)
def retrieve(conversation_id: int, tenant: TenantContext = Depends(resolve_tenant_from_jwt), db: Session = Depends(get_db)):
    conversation = get_conversation(db, tenant, conversation_id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
def messages(
    conversation_id: int,
    limit: int = Query(default=100, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    limit = min(limit, settings.max_page_size)
    items, total = list_messages(db, tenant, conversation_id, limit, offset)
    return MessageListResponse(items=items, total=total, limit=limit, offset=offset)

