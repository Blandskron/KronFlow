from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChannelConnectionCreateIn(BaseModel):
    channel: Literal["email", "whatsapp"]
    provider: Literal["stub", "resend", "whatsapp_business_official"]
    sender_address: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=120)
    verified: bool = False
    sandbox_only: bool = True
    provider_secret: str | None = Field(default=None, max_length=255)


class ChannelConnectionRotateIn(BaseModel):
    new_provider_secret: str = Field(min_length=1, max_length=255)


class ChannelConnectionOut(BaseModel):
    id: int
    channel: str
    provider: str
    sender_address: str
    display_name: str
    status: str
    verified: bool
    sandbox_only: bool
    credential_version: int
    revoked_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class TemplateCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    channel: Literal["email", "whatsapp"]
    language: str = Field(default="es", min_length=2, max_length=16)
    subject: str | None = Field(default=None, max_length=200)
    body_text: str = Field(min_length=1, max_length=10000)
    body_html: str | None = Field(default=None, max_length=20000)
    declared_variables: list[str] = Field(default_factory=list)
    approve_immediately: bool = False


class TemplateOut(BaseModel):
    template_id: int
    template_version_id: int
    name: str
    channel: str
    language: str
    version: int
    status: str
    subject: str | None = None
    declared_variables: list[str]


class CampaignCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    channel: Literal["email", "whatsapp"]
    purpose: str = Field(min_length=1, max_length=64)
    template_version_id: int = Field(ge=1)
    connection_id: int = Field(ge=1)
    segment_filter: dict = Field(default_factory=dict)
    timezone_iana: str = Field(default="UTC", min_length=1, max_length=64)


class CampaignApproveIn(BaseModel):
    expected_version: int = Field(ge=1)
    scheduled_at: datetime | None = None


class CampaignStateIn(BaseModel):
    expected_version: int = Field(ge=1)


class CampaignOut(BaseModel):
    id: int
    name: str
    channel: str
    purpose: str
    template_version_id: int
    connection_id: int
    timezone_iana: str
    status: str
    version: int
    scheduled_at: datetime | None = None
    recipient_counts: dict[str, int] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CampaignDispatchOut(BaseModel):
    claimed: int
    accepted: int
    suppressed: int
    skipped_paused: int


class ChannelReceiptIn(BaseModel):
    provider_account_id: str = Field(min_length=1, max_length=80)
    provider_event_id: str = Field(min_length=1, max_length=180)
    event_type: Literal["accepted", "delivered", "bounced", "complained", "unsubscribed"]
    provider_message_id: str | None = Field(default=None, max_length=220)
    destination: str | None = Field(default=None, max_length=255)
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime | None = None


class ChannelReceiptOut(BaseModel):
    duplicate: bool
    event_id: int | None = None


class UnsubscribeIn(BaseModel):
    channel: Literal["email", "whatsapp"]
    destination: str = Field(min_length=3, max_length=255)
    purpose: str | None = Field(default=None, max_length=64)


class UnsubscribeOut(BaseModel):
    status: Literal["unsubscribed"]


class UnsubscribeTokenCreateIn(BaseModel):
    channel: Literal["email", "whatsapp"]
    destination: str = Field(min_length=3, max_length=255)
    purpose: str | None = Field(default=None, max_length=64)
    client_id: int | None = Field(default=None, ge=1)
    ttl_days: int = Field(default=90, ge=1, le=365)


class UnsubscribeTokenOut(BaseModel):
    token: str
    channel: str
    destination: str
    purpose: str | None = None
    expires_at: datetime


class ConversationEmailIn(BaseModel):
    connection_id: int = Field(ge=1)
    to_email: str = Field(min_length=3, max_length=254)
    subject: str = Field(min_length=1, max_length=200)
    body_text: str = Field(min_length=1, max_length=10000)
    idempotency_key: str = Field(min_length=1, max_length=120)


class ConversationEmailOut(BaseModel):
    status: Literal["queued"]
    duplicate: bool
    outbox_job_id: int
    message_id: int | None = None
    conversation_id: int
    connection_id: int
