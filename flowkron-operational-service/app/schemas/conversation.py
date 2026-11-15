from datetime import datetime

from pydantic import BaseModel


class ConversationOut(BaseModel):
    id: int
    lead_id: int
    lead_name: str
    lead_phone: str
    channel: str
    external_thread_id: str
    status: str
    requires_human: bool
    last_message_at: datetime | None
    last_message: str | None = None
    temperature: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    external_message_id: str
    sender_type: str
    body: str
    raw_payload: dict
    sent_at: datetime
    created_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationOut]
    total: int
    limit: int
    offset: int


class MessageListResponse(BaseModel):
    items: list[MessageOut]
    total: int
    limit: int
    offset: int

