from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class ContextChunkCreate(BaseModel):
    chunk_index: int
    content: str
    token_count: int
    source_ref: str = ""


class ContextDocumentCreate(BaseModel):
    tenant_id: str
    title: str
    filename: str
    content_type: str = "text/plain"
    status: str = "active"
    priority: int = 100
    raw_text: str
    chunks: list[ContextChunkCreate] = Field(default_factory=list)


class ContextDocumentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=220)
    status: str | None = Field(default=None, max_length=32)
    priority: int | None = None


class ContextDocumentRead(BaseModel):
    id: int
    tenant_id: str
    title: str
    filename: str
    content_type: str | None = None
    status: str
    priority: int
    version: int
    source_type: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class BusinessContextStatusRead(BaseModel):
    progress_percent: int
    agent_status: str
    last_updated_at: str | None
    active_documents_count: int
    documents: list[ContextDocumentRead]
    document_actions: dict[str, bool] = Field(default_factory=dict)


class ContextRetrieveRequest(BaseModel):
    query: str
    limit: int = 3
    document_ids: list[int] | None = None


class ContextSourceRead(BaseModel):
    document_id: int
    chunk_id: int
    title: str
    score: float
    content: str


class AgentRuleCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    rule_type: str = Field(default="general", max_length=48)
    content: str = Field(min_length=1)
    priority: int = 100
    is_active: bool = True
    agent_id: int | None = None


class AgentRulePatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    content: str | None = Field(default=None, min_length=1)
    priority: int | None = None
    is_active: bool | None = None


class AgentRuleOut(BaseModel):
    id: int
    tenant_id: str
    agent_id: int | None = None
    name: str
    rule_type: str
    content: str
    priority: int
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentTraceCreateIn(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    agent_id: int | None = None
    agent_revision_id: int | None = None
    query: str
    output_message: str
    confidence: float = 0.0
    requires_human: bool = False
    is_simulation: bool = False
    sources: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)


class AgentTraceOut(BaseModel):
    id: int
    tenant_id: str
    conversation_id: str
    agent_id: int | None = None
    agent_revision_id: int | None = None
    query: str
    output_message: str
    confidence: float
    requires_human: bool
    is_simulation: bool
    sources: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    correlation_id: str | None = None
    created_at: datetime | None = None


class SetupSessionCreateIn(BaseModel):
    objective: str = Field(default="build_business_context", max_length=120)


class SetupMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class SetupSessionOut(BaseModel):
    session_id: str
    next_question: str


class SetupGenerateOut(BaseModel):
    summary: str
    status: str = "draft"
    document_id: int | None = None


class ActiveAgentResolvedOut(BaseModel):
    agent_id: int
    agent_revision_id: int
    revision_number: int
    name: str
    role: str
    tone: str
    language: str
    instructions: str
    allowed_tools: list[str]
    allowed_document_ids: list[int]
    limits: dict[str, Any]


class InternalProposalCreateIn(BaseModel):
    action_type: str
    resource_id: int = Field(ge=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=180)
    proposed_by: str = Field(default="agent-core", max_length=64)
    rationale: str | None = Field(default=None, max_length=500)


class InternalAIUsageCreateIn(BaseModel):
    provider: str = Field(min_length=1, max_length=48)
    model: str = Field(min_length=1, max_length=80)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    estimated_cost_usd: Decimal = Field(ge=0)
    is_simulation: bool = False
    agent_id: int | None = None
    agent_revision_id: int | None = None
    pricing_version: str | None = Field(default=None, max_length=32)
