from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class HandoffHistoryItem(BaseModel):
    id: int
    kind: Literal["whatsapp_turn", "inbound_handoff"]
    occurred_at: datetime
    conversation_id: int | None
    lead_id: int | None
    contact_name: str | None


class HandoffHistoryPage(BaseModel):
    items: list[HandoffHistoryItem]
    next_before_id: int | None


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


class ConversationControlOut(BaseModel):
    conversation_id: int
    mode: Literal["ai_active", "waiting_human", "human_active", "resolved"]
    owner_user_id: str | None = None
    ai_enabled: bool
    tenant_ai_enabled: bool
    control_version: int
    handoff_reason: str | None = None
    resolution_reason: str | None = None
    updated_by: str | None = None
    updated_at: datetime
    cancelled_ai_turns: int = 0


class ConversationHandoffIn(BaseModel):
    reason: str = Field(min_length=1, max_length=180)
    expected_version: int | None = Field(default=None, ge=1)


class ConversationClaimIn(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=180)


class ConversationReturnToAIIn(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=180)


class ConversationResolveIn(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=180)


class HumanReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=120)


class HumanReplyOut(BaseModel):
    status: Literal["queued"]
    duplicate: bool
    outbox_job_id: int
    message_id: int | None = None
    conversation_id: int
    control_version: int


class AgentHandoffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_agent_id: int = Field(ge=1)
    from_agent_id: int | None = Field(default=None, ge=1)
    reason: str = Field(min_length=2, max_length=240)
    shared_summary: str = Field(default="", max_length=1000)
    max_hops: int = Field(default=3, ge=1, le=5)


class AgentHandoffItemOut(BaseModel):
    trace_id: int
    conversation_id: int
    from_agent_id: int | None = None
    to_agent_id: int | None = None
    to_agent_revision_id: int | None = None
    hop_number: int
    reason: str
    shared_summary: str
    actor_user_id: str | None = None
    created_at: datetime


class AgentHandoffResultOut(AgentHandoffItemOut):
    max_hops: int


