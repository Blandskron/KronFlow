"""Pydantic schemas for outbound WhatsApp Cloud API, Google Calendar OAuth sync, and HubSpot CRM sync."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WhatsAppCloudSendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone_number_id: str = Field(min_length=1, max_length=128)
    to_phone: str = Field(min_length=4, max_length=40)
    client_id: int | None = Field(default=None, ge=1)
    body_text: str | None = Field(default=None, max_length=4096)
    template_name: str | None = Field(default=None, max_length=128)
    template_language: str = Field(default="es", min_length=2, max_length=16)
    outside_24h_window: bool = False
    idempotency_key: str = Field(min_length=3, max_length=180)
    access_token: str | None = Field(default=None, max_length=1000)


class WhatsAppCloudSendOut(BaseModel):
    duplicate: bool
    message_id: int
    provider_message_id: str | None = None
    connection_id: str
    status: str


class GoogleCalendarPushIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calendar_id: str = Field(default="primary", min_length=1, max_length=160)
    access_token: str | None = Field(default=None, max_length=1000)


class GoogleCalendarSyncIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calendar_id: str = Field(default="primary", min_length=1, max_length=160)
    access_token: str | None = Field(default=None, max_length=1000)
    force_full_resync: bool = False


class HubSpotSyncIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stream: Literal["contacts", "deals"] = "contacts"
    batch_size: int = Field(default=25, ge=1, le=50)
    access_token: str | None = Field(default=None, max_length=1000)


class ConnectorSyncResultOut(BaseModel):
    provider: str
    stream: str
    status: str
    synced: int = 0
    conflicts: int = 0
    cursor_reset: bool = False
    rate_limited: bool = False
    retry_after_seconds: int | None = None
    cursor_value: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None
