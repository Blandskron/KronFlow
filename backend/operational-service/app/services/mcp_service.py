"""Governed MCP JSON-RPC 2.0 server wrapping KronFlow's Tool Hub with scopes and idempotency."""

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.mcp import JsonRpcRequestIn
from app.services.tool_hub_service import invoke_tool, list_tools


MCP_PROTOCOL_VERSION = "2025-03-26"


def handle_mcp_request(
    db: Session,
    tenant: TenantContext,
    rpc_req: JsonRpcRequestIn,
    *,
    actor_user_id: str,
    allowed_scopes: set[str] | None = None,
    header_idempotency_key: str | None = None,
) -> dict[str, Any]:
    method = rpc_req.method.strip()

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rpc_req.id,
            "result": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "serverInfo": {"name": "kronflow-operational-mcp", "version": "1.0.0"},
                "capabilities": {"tools": {"listChanged": False}},
            },
        }

    if method == "tools/list":
        tools = [item for item in list_tools(db, tenant) if item["is_enabled"]]
        return {
            "jsonrpc": "2.0",
            "id": rpc_req.id,
            "result": {
                "tools": [
                    {
                        "name": item["tool_key"],
                        "description": item["description"],
                        "inputSchema": item["input_schema"],
                        "_meta": {
                            "effect_mode": item["effect_mode"],
                            "schema_version": item["schema_version"],
                            "max_calls_per_hour": item["max_calls_per_hour"],
                        },
                    }
                    for item in tools
                ]
            },
        }

    if method == "tools/call":
        if allowed_scopes is not None and "mcp:invoke" not in allowed_scopes:
            raise HTTPException(status_code=403, detail="Credential lacks 'mcp:invoke' scope")

        params = dict(rpc_req.params or {})
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            return {
                "jsonrpc": "2.0",
                "id": rpc_req.id,
                "error": {"code": -32602, "message": "params.name is required"},
            }

        raw_args = dict(params.get("arguments") or {})
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        idem_key = (
            (header_idempotency_key or "").strip()
            or str(meta.get("idempotency_key") or "").strip()
            or str(raw_args.pop("_idempotency_key", "") or "").strip()
            or f"mcp:{rpc_req.id if rpc_req.id is not None else 'auto'}"
        )
        expected_version = meta.get("expected_schema_version")
        if type(expected_version) is not int:
            expected_version = None

        try:
            inv = invoke_tool(
                db,
                tenant,
                tool_key=tool_name,
                arguments=raw_args,
                idempotency_key=idem_key,
                actor_user_id=actor_user_id,
                expected_schema_version=expected_version,
            )
        except HTTPException as exc:
            if exc.status_code in (401, 403):
                raise
            return {
                "jsonrpc": "2.0",
                "id": rpc_req.id,
                "error": {"code": -32000 - exc.status_code, "message": str(exc.detail)},
            }

        return {
            "jsonrpc": "2.0",
            "id": rpc_req.id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "invocation_id": inv["id"],
                                "tool_key": inv["tool_key"],
                                "status": inv["status"],
                                "effect_mode": inv["effect_mode"],
                                "proposal_id": inv["proposal_id"],
                                "outbox_job_id": inv["outbox_job_id"],
                                "duplicate": inv["duplicate"],
                                "result": inv["result_json"],
                            },
                            ensure_ascii=False,
                        ),
                    }
                ],
                "isError": False,
                "structuredContent": inv["result_json"],
                "_meta": {
                    "invocation_id": inv["id"],
                    "status": inv["status"],
                    "proposal_id": inv["proposal_id"],
                    "outbox_job_id": inv["outbox_job_id"],
                },
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": rpc_req.id,
        "error": {"code": -32601, "message": f"Method '{method}' not found"},
    }
