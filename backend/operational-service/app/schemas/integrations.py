"""Pydantic schemas for Meta omnichannel webhooks, external entity sync mappings, and cursors."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChannelWebhookRouteCreateIn(BaseModel):
    channel: Literal["whatsapp", "instagram", "messenger", "shopify", "mercadopago", "voice_twilio"]
    external_account_id: str = Field(min_length=1, max_length=128)
    connection_id: int | None = Field(default=None, ge=1)
    verify_token: str = Field(min_length=8, max_length=255)
    app_secret: str = Field(min_length=8, max_length=255)


class ChannelWebhookRouteOut(BaseModel):
    id: int
    channel: str
    provider: str
    external_account_id: str
    connection_id: int | None = None
    secret_fingerprint: str
    is_active: bool
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ExternalMappingUpsertIn(BaseModel):
    connection_ref: str = Field(min_length=1, max_length=80)
    resource_type: str = Field(min_length=1, max_length=32)
    remote_id: str = Field(min_length=1, max_length=160)
    local_type: str = Field(min_length=1, max_length=32)
    local_id: str = Field(min_length=1, max_length=64)
    remote_version: str | None = Field(default=None, max_length=64)
    expected_local_version: int | None = Field(default=None, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class ExternalMappingResolveIn(BaseModel):
    resolution: Literal["synced", "disconnected"] = "synced"
    local_id: str | None = Field(default=None, min_length=1, max_length=64)
    remote_version: str | None = Field(default=None, max_length=64)


class ExternalMappingOut(BaseModel):
    id: int
    connection_ref: str
    resource_type: str
    remote_id: str
    local_type: str
    local_id: str
    remote_version: str | None = None
    local_version: int
    sync_state: str
    conflict_payload: dict[str, Any]
    owner_user_id: str | None = None
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime


class SyncCursorUpsertIn(BaseModel):
    connection_ref: str = Field(min_length=1, max_length=80)
    stream_name: str = Field(min_length=1, max_length=64)
    cursor_value: str = Field(min_length=1, max_length=255)
    status: Literal["ok", "error", "paused"] = "ok"
    last_error: str | None = Field(default=None, max_length=300)
    synced_count: int = Field(default=0, ge=0)


class SyncCursorOut(BaseModel):
    id: int
    connection_ref: str
    stream_name: str
    cursor_value: str
    status: str
    last_error: str | None = None
    synced_count: int
    updated_at: datetime
