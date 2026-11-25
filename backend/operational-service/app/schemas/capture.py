from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BackfillContactPointsOut(BaseModel):
    inserted: int
    skipped_existing: int
    collisions: int
    unresolved: int


class ScopedCredentialCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(min_length=1)
    expires_at: datetime | None = None


class ScopedCredentialOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    api_key: str | None = None
    scopes: list[str]
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime | None = None


class PublicFormCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    source_label: str = Field(default="web_form", min_length=1, max_length=48)
    allowed_fields: list[str] | None = None


class PublicFormOut(BaseModel):
    id: int
    name: str
    form_token: str
    source_label: str
    allowed_fields: list[str]
    is_active: bool
    created_at: datetime


class LeadCaptureIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=80)
    message: str | None = Field(default=None, max_length=2000)
    marketing_opt_in: bool = False
    website: str | None = Field(default=None, max_length=120)  # honeypot for public forms


class LeadCaptureAcceptedOut(BaseModel):
    status: Literal["accepted"]
    capture_id: int | None = None
    duplicate: bool = False


class DomainEventOut(BaseModel):
    id: int
    event_id: str
    event_type: str
    schema_version: int
    tenant_id: str
    aggregate_type: str
    aggregate_id: str
    correlation_id: str
    payload: dict
    occurred_at: datetime


class DomainEventReplayOut(BaseModel):
    items: list[DomainEventOut]
    next_after_id: int
    has_more: bool


class DomainEventSubscriptionUpsertIn(BaseModel):
    subscriber_name: str = Field(min_length=1, max_length=64)
    event_types: list[str] = Field(default_factory=list)
    is_active: bool = True


class DomainEventSubscriptionOut(BaseModel):
    id: int
    subscriber_name: str
    event_types: list[str]
    last_event_id: int
    is_active: bool
    updated_at: datetime


class DomainEventPollOut(DomainEventReplayOut):
    subscriber_name: str
    checkpoint_id: int


class DomainEventAckIn(BaseModel):
    through_event_id: int = Field(ge=0)
