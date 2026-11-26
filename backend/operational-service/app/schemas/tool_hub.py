"""Pydantic schemas for governed tool registry and idempotent tool invocations."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCreateIn(BaseModel):
    tool_key: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=400)
    effect_mode: Literal["read_only", "proposal_required", "outbox_async"] = "read_only"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    required_permission: str = Field(default="crm.manage", min_length=1, max_length=64)
    connector_ref: str | None = Field(default=None, max_length=80)
    is_enabled: bool = True
    max_calls_per_hour: int = Field(default=120, ge=1, le=5000)


class ToolUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=400)
    effect_mode: Literal["read_only", "proposal_required", "outbox_async"] | None = None
    input_schema: dict[str, Any] | None = None
    required_permission: str | None = Field(default=None, min_length=1, max_length=64)
    connector_ref: str | None = Field(default=None, max_length=80)
    is_enabled: bool | None = None
    max_calls_per_hour: int | None = Field(default=None, ge=1, le=5000)


class ToolOut(BaseModel):
    id: int
    tool_key: str
    name: str
    description: str
    effect_mode: str
    schema_version: int
    input_schema: dict[str, Any]
    required_permission: str
    connector_ref: str | None = None
    is_enabled: bool
    max_calls_per_hour: int
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ToolInvocationCreateIn(BaseModel):
    tool_key: str = Field(min_length=2, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=180)
    expected_schema_version: int | None = Field(default=None, ge=1)


class ToolInvocationOut(BaseModel):
    id: int
    tool_id: int
    tool_key: str
    schema_version: int
    idempotency_key: str
    arguments_json: dict[str, Any]
    effect_mode: str
    status: str
    result_json: dict[str, Any]
    proposal_id: int | None = None
    outbox_job_id: int | None = None
    invoked_by: str
    correlation_id: str | None = None
    created_at: datetime
    duplicate: bool = False
