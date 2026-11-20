from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    no_leidos: int = 0


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    external_message_id: str
    sender_type: str
    body: str
    raw_payload: dict
    sent_at: datetime
    created_at: datetime
    connection_id: str = "default"
    channel: str = "whatsapp"
    provider_message_id: str | None = None
    direction: str
    message_type: str = "text"
    delivery_status: str = "unknown"
    delivery_failure_reason: str | None = None
    recorded_at: datetime


class ConversationCursor(BaseModel):
    before_at: datetime
    before_id: int


class ConversationListResponse(BaseModel):
    items: list[ConversationOut]
    total: int
    limit: int
    offset: int
    next_cursor: ConversationCursor | None = None


class ConversationReadIn(BaseModel):
    through_message_id: int = Field(gt=0)


class ConversationReadOut(BaseModel):
    no_leidos: int


class PendingReplyOut(BaseModel):
    inbound_message_id: int
    status: Literal["queued", "sending", "unknown", "not_sent"]


class MessageListResponse(BaseModel):
    items: list[MessageOut]
    total: int
    limit: int
    offset: int
    pending_replies: list[PendingReplyOut] = Field(default_factory=list)

