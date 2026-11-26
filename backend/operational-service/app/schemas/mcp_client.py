"""Pydantic schemas for tenant-scoped approved remote MCP servers and invocations."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RemoteMcpServerCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server_key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$")
    name: str = Field(min_length=2, max_length=160)
    base_url: str = Field(min_length=8, max_length=500)
    auth_header_name: str = Field(default="Authorization", min_length=2, max_length=64)
    auth_token: str | None = Field(default=None, max_length=500)
    allowed_tools: list[str] = Field(default_factory=list, max_length=50)


class RemoteMcpServerOut(BaseModel):
    id: int
    server_key: str
    name: str
    base_url: str
    auth_header_name: str
    auth_fingerprint: str | None = None
    allowed_tools: list[str] = []
    discovered_tools: list[dict[str, Any]] = []
    is_active: bool
    revoked_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class RemoteMcpInvokeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=3, max_length=180)


class RemoteMcpInvokeOut(BaseModel):
    invocation_id: int
    server_key: str
    tool_name: str
    status: str
    duplicate: bool
    result: dict[str, Any]
