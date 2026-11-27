"""Pydantic schemas for embeddable webchat widgets, visitor sessions, and cursor polling."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WebchatWidgetCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    allowed_origins: list[str] = Field(min_length=1, max_length=20)
    agent_id: int | None = Field(default=None, ge=1)
    welcome_message: str = Field(default="¡Hola! ¿En qué podemos ayudarte hoy?", min_length=1, max_length=300)
    session_ttl_minutes: int = Field(default=120, ge=5, le=1440)
    rate_limit_per_minute: int = Field(default=30, ge=1, le=300)
    is_active: bool = True


class WebchatWidgetUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    allowed_origins: list[str] | None = Field(default=None, min_length=1, max_length=20)
    agent_id: int | None = Field(default=None, ge=1)
    welcome_message: str | None = Field(default=None, min_length=1, max_length=300)
    session_ttl_minutes: int | None = Field(default=None, ge=5, le=1440)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=300)
    is_active: bool | None = None


class WebchatWidgetOut(BaseModel):
    id: int
    widget_key: str
    name: str
    is_active: bool
    allowed_origins: list[str]
    agent_id: int | None = None
    welcome_message: str
    session_ttl_minutes: int
    rate_limit_per_minute: int
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class WebchatSessionCreateIn(BaseModel):
    visitor_name: str | None = Field(default=None, max_length=160)
    visitor_email: str | None = Field(default=None, max_length=180)


WEBCHAT_AI_DISCLOSURE = (
    "Estás interactuando con un asistente automatizado de Inteligencia Artificial (EU AI Act Art. 50). "
    "Puedes solicitar atención humana en cualquier momento."
)


class WebchatSessionOut(BaseModel):
    session_token: str
    conversation_id: int
    welcome_message: str
    ai_disclosure: str = WEBCHAT_AI_DISCLOSURE
    cursor: int
    expires_at: datetime


class WebchatMessageCreateIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=120)


class WebchatMessageItemOut(BaseModel):
    id: int
    direction: str
    sender_role: str
    body: str
    delivery_status: str
    created_at: datetime | None = None


class WebchatMessagePostOut(BaseModel):
    conversation_id: int
    inbound_message: WebchatMessageItemOut
    reply_message: WebchatMessageItemOut | None = None
    ai_paused: bool = False
    control_mode: str = "ai_active"
    cursor: int
    duplicate: bool = False


class WebchatMessageListOut(BaseModel):
    conversation_id: int
    items: list[WebchatMessageItemOut]
    next_cursor: int
    has_more: bool
    control_mode: str
