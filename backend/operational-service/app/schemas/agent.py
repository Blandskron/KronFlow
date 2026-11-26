from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentConfigureRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    role: str = Field(min_length=1, max_length=160)
    prompt_config: dict[str, Any] = Field(default_factory=dict)
    tone: str = Field(default="professional", min_length=1, max_length=120)
    language: str = Field(default="es", min_length=2, max_length=16)
    instructions: str = Field(default="", max_length=12000)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_document_ids: list[int] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)
    is_default: bool | None = None


class AgentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    role: str | None = Field(default=None, min_length=1, max_length=160)
    status: Literal["draft", "active", "archived"] | None = None
    prompt_config: dict[str, Any] | None = None
    tone: str | None = Field(default=None, min_length=1, max_length=120)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    instructions: str | None = Field(default=None, max_length=12000)
    allowed_tools: list[str] | None = None
    allowed_document_ids: list[int] | None = None
    limits: dict[str, Any] | None = None
    is_default: bool | None = None
    expected_version: int | None = Field(default=None, ge=1)


class AgentPublishRequest(BaseModel):
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=240)


class AgentRollbackRequest(BaseModel):
    expected_version: int = Field(ge=1)
    revision_id: int = Field(ge=1)


class AgentRevisionOut(BaseModel):
    id: int
    agent_id: int
    revision_number: int
    status: str
    name: str
    role: str
    tone: str
    language: str
    instructions: str
    allowed_tools: list[str]
    allowed_document_ids: list[int]
    limits: dict[str, Any]
    prompt_config: dict[str, Any]
    publish_note: str | None = None
    published_by: str | None = None
    published_at: datetime


class AgentOut(BaseModel):
    id: int
    name: str
    role: str
    status: str
    tone: str = "professional"
    language: str = "es"
    instructions: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_document_ids: list[int] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)
    prompt_config: dict[str, Any]
    is_default: bool = False
    version: int = 1
    active_revision_id: int | None = None
    active_revision_number: int | None = None
    created_at: datetime
    updated_at: datetime
