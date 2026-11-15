from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas.agent import AgentMessageRequest, AgentMessageResponse
from app.application.orchestration.agent_runtime import process_agent_message, process_stateless_agent_message
from app.core.config import get_settings
from app.core.database import get_db
from app.core.tenant import TenantContext, resolve_tenant
from app.models.conversation import ConversationMessage, ConversationSession

router = APIRouter(prefix="/api/v1/agent", tags=["Agent Runtime"])


def _assert_payload_tenant(payload_tenant_id: str | None, tenant: TenantContext) -> None:
    if payload_tenant_id and payload_tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Payload tenant does not match authenticated tenant")


@router.post("/messages", response_model=AgentMessageResponse)
def receive_message(payload: AgentMessageRequest, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    _assert_payload_tenant(payload.tenant_id, tenant)
    if get_settings().persistence_mode == "operational":
        return process_stateless_agent_message(tenant.tenant_id, payload)
    return process_agent_message(db, tenant.tenant_id, payload)


@router.post("/simulate", response_model=AgentMessageResponse)
def simulate_message(payload: AgentMessageRequest, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    _assert_payload_tenant(payload.tenant_id, tenant)
    if get_settings().persistence_mode == "operational":
        return process_stateless_agent_message(tenant.tenant_id, payload)
    return process_agent_message(db, tenant.tenant_id, payload)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    conversation = db.scalar(select(ConversationSession).where(ConversationSession.tenant_id == tenant.tenant_id, ConversationSession.external_conversation_id == conversation_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"id": conversation.id, "conversation_id": conversation.external_conversation_id, "channel": conversation.channel, "requires_human": conversation.requires_human, "status": conversation.status}


@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    conversation = db.scalar(select(ConversationSession).where(ConversationSession.tenant_id == tenant.tenant_id, ConversationSession.external_conversation_id == conversation_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = db.scalars(select(ConversationMessage).where(ConversationMessage.tenant_id == tenant.tenant_id, ConversationMessage.conversation_id == conversation.id).order_by(ConversationMessage.id)).all()
    return [{"sender_type": msg.sender_type, "message_type": msg.message_type, "content": msg.content, "attachments": msg.attachments} for msg in messages]
