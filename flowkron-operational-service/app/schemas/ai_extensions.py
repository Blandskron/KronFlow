from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ConversationMemoryCreateIn(BaseModel):
    memory_key: str = Field(min_length=1, max_length=64)
    memory_value: str = Field(min_length=1, max_length=2000)
    source_type: Literal["message", "operator", "document", "system"]
    source_ref: str = Field(min_length=1, max_length=120)
    ttl_days: int = Field(default=30, ge=1, le=365)


class ConversationMemoryOut(BaseModel):
    id: int
    conversation_id: int
    memory_key: str
    memory_value: str
    source_type: str
    source_ref: str
    expires_at: datetime
    created_at: datetime


class ContactEnrichmentCreateIn(BaseModel):
    field_name: Literal["nombre", "email", "telefono"]
    proposed_value: str = Field(min_length=1, max_length=255)
    source: str = Field(default="agent-core", min_length=1, max_length=64)


class ContactEnrichmentApplyIn(BaseModel):
    allow_overwrite: bool = False


class ContactEnrichmentOut(BaseModel):
    id: int
    client_id: int
    field_name: str
    proposed_value: str
    previous_value: str | None = None
    source: str
    status: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class ExternalNotificationCreateIn(BaseModel):
    dedup_key: str = Field(min_length=1, max_length=180)
    event_type: str = Field(min_length=1, max_length=64)
    channel: Literal["email", "webhook_stub"]
    recipient: str = Field(min_length=1, max_length=255)
    payload: dict = Field(default_factory=dict)


class ExternalNotificationReceiptIn(BaseModel):
    status: Literal["delivered", "failed"]
    receipt_ref: str | None = Field(default=None, max_length=180)


class ExternalNotificationOut(BaseModel):
    id: int
    dedup_key: str
    status: str
    outbox_job_id: int | None = None
    receipt_ref: str | None = None
    duplicate: bool = False


class AIUsageCreateIn(BaseModel):
    provider: str = Field(min_length=1, max_length=48)
    model: str = Field(min_length=1, max_length=80)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    estimated_cost_usd: Decimal = Field(ge=0)
    correlation_id: str | None = Field(default=None, max_length=64)


class AIUsageOut(BaseModel):
    id: int
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    estimated_cost_usd: str
    correlation_id: str | None = None
    recorded_at: datetime


class AIUsageSummaryOut(BaseModel):
    days: int
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_cost_usd: str
    avg_latency_ms: float
