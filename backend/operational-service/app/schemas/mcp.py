"""Pydantic schemas for KronFlow governed MCP JSON-RPC 2.0 server."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class JsonRpcRequestIn(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    method: str = Field(min_length=1, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcErrorOut(BaseModel):
    code: int
    message: str
    data: Any = None


class JsonRpcResponseOut(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    result: dict[str, Any] | None = None
    error: JsonRpcErrorOut | None = None
