from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WebhookSubscriptionCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    target_url: str = Field(min_length=8, max_length=500)
    event_types: list[str] = Field(default_factory=list)
    max_attempts: int = Field(default=5, ge=1, le=10)


class WebhookSubscriptionOut(BaseModel):
    id: int
    name: str
    target_url: str
    signing_secret: str
    event_types: list[str]
    is_active: bool
    max_attempts: int
    created_at: datetime


class WebhookDeliveryEnqueueIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)
    event_type: str = Field(min_length=1, max_length=80)
    payload: dict


class WebhookDeliveryAttemptIn(BaseModel):
    http_status: int | None = Field(default=None, ge=100, le=599)
    error: str | None = Field(default=None, max_length=160)


class WebhookDeliveryOut(BaseModel):
    id: int
    subscription_id: int
    event_id: str
    event_type: str
    signature: str
    status: str
    attempts: int
    last_http_status: int | None = None
    last_error: str | None = None
    outbox_job_id: int | None = None
    duplicate: bool = False


class PrivateAttachmentCreateIn(BaseModel):
    resource_type: Literal["conversation", "contact", "opportunity"]
    resource_id: int = Field(ge=1)
    filename: str = Field(min_length=1, max_length=180)
    content_type: str = Field(min_length=3, max_length=80)
    size_bytes: int = Field(ge=1, le=10485760)
    sha256_hex: str = Field(min_length=64, max_length=64)
    retention_days: int = Field(default=90, ge=1, le=3650)


class PrivateAttachmentOut(BaseModel):
    id: int
    resource_type: str
    resource_id: int
    filename: str
    content_type: str
    size_bytes: int
    sha256_hex: str
    storage_key: str
    uploaded_by: str | None = None
    expires_at: datetime
    created_at: datetime


class AppointmentSimulateIn(BaseModel):
    resource_key: str = Field(min_length=1, max_length=64)
    starts_at: datetime
    ends_at: datetime


class AppointmentSimulateOut(BaseModel):
    available: bool
    conflict_ids: list[int]


class AppointmentConfirmIn(BaseModel):
    resource_key: str = Field(min_length=1, max_length=64)
    client_id: int = Field(ge=1)
    conversation_id: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=160)
    starts_at: datetime
    ends_at: datetime
    idempotency_key: str = Field(min_length=1, max_length=180)


class AppointmentOut(BaseModel):
    id: int
    resource_key: str
    client_id: int
    conversation_id: int | None = None
    title: str
    starts_at: datetime
    ends_at: datetime
    status: str
    idempotency_key: str
    duplicate: bool = False
