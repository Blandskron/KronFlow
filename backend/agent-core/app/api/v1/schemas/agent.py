from typing import Any, Literal

from pydantic import BaseModel, Field


Channel = Literal["whatsapp", "instagram", "facebook", "tiktok", "webchat", "email", "voice", "other"]
MessageType = Literal["text", "audio", "image", "file"]
ActionType = Literal[
    "create_lead",
    "schedule_meeting",
    "send_email",
    "handoff_human",
    "create_ticket",
    "crm.contact.rename",
    "crm.lead.update_stage",
    "crm.opportunity.add_note",
    "crm.conversation.request_handoff",
    "none",
]
NextStep = Literal["continue_conversation", "wait_user", "handoff", "close"]


class CustomerPayload(BaseModel):
    external_id: str
    name: str | None = None
    phone: str | None = None
    email: str | None = None


class MessagePayload(BaseModel):
    type: MessageType = "text"
    content: str
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class MessageMetadata(BaseModel):
    timestamp: str | None = None
    source_url: str | None = None
    campaign_id: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class AgentMessageRequest(BaseModel):
    tenant_id: str | None = None
    channel: Channel
    conversation_id: str
    customer: CustomerPayload
    message: MessagePayload
    metadata: MessageMetadata = Field(default_factory=MessageMetadata)
    agent_id: int | None = None
    agent_revision_id: int | None = None


class ReplyPayload(BaseModel):
    type: Literal["text"] = "text"
    content: str


class AgentActionPayload(BaseModel):
    type: ActionType
    payload: dict[str, Any] = Field(default_factory=dict)


class SourcePayload(BaseModel):
    source_id: str
    document_id: str | None = None
    chunk_id: str | None = None
    title: str
    score: float
    page: int | None = None
    uri: str | None = None


AI_DISCLOSURE_NOTICE = (
    "Estás interactuando con un asistente automatizado de Inteligencia Artificial (EU AI Act Art. 50). "
    "Puedes solicitar atención humana en cualquier momento."
)


class AgentMessageResponse(BaseModel):
    tenant_id: str
    conversation_id: str
    reply: ReplyPayload
    actions: list[AgentActionPayload]
    requires_human: bool
    confidence: float
    sources: list[SourcePayload]
    next_step: NextStep
    agent_id: int | None = None
    agent_revision_id: int | None = None
    ai_disclosure: str = AI_DISCLOSURE_NOTICE
