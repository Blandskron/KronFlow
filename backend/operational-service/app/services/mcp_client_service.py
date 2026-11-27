"""Tenant-scoped remote MCP client with SSRF validation, allowlist enforcement, and idempotent invocations."""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable
import urllib.error
import urllib.request

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_value, encrypt_value
from app.core.pii_scrubber import scrub_payload
from app.core.tenant_resolver import TenantContext
from app.schemas.mcp_client import RemoteMcpInvokeIn, RemoteMcpServerCreateIn
from app.services.conversation_control_service import is_external_ai_transfer_allowed_in_tx
from app.services.post_v1_service import _validate_webhook_url
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.phase4_hub import ToolDefinition, ToolInvocation
from app.tenant_models.phase6_extensions import RemoteMcpServer


JsonRpcTransport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Remote MCP timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _require_mcp_client_ready(db: Session, tenant: TenantContext) -> None:
    inspector = inspect(db.connection())
    existing = set(inspector.get_table_names(schema=tenant.schema_name))
    if not {RemoteMcpServer.__tablename__, ToolDefinition.__tablename__, ToolInvocation.__tablename__}.issubset(existing):
        raise HTTPException(status_code=503, detail="Remote MCP client schema is unavailable")


def _server_to_dict(row: RemoteMcpServer) -> dict[str, Any]:
    return {
        "id": row.id,
        "server_key": row.server_key,
        "name": row.name,
        "base_url": row.base_url,
        "auth_header_name": row.auth_header_name,
        "auth_fingerprint": row.auth_fingerprint,
        "allowed_tools": list(row.allowed_tools or []),
        "discovered_tools": list(row.discovered_tools or []),
        "is_active": row.is_active,
        "revoked_at": row.revoked_at,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _default_jsonrpc_transport(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    _validate_webhook_url(url)
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"result": parsed}
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Remote MCP server returned HTTP {exc.code}") from None
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"Remote MCP transport failed: {exc}") from None


def list_remote_mcp_servers(db: Session, tenant: TenantContext) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    _require_mcp_client_ready(db, tenant)
    rows = list(db.scalars(select(RemoteMcpServer).order_by(RemoteMcpServer.id.asc())).all())
    return [_server_to_dict(row) for row in rows]


def register_remote_mcp_server(
    db: Session,
    tenant: TenantContext,
    payload: RemoteMcpServerCreateIn,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    safe_url = _validate_webhook_url(payload.base_url)
    bind_tenant_session(db, tenant.schema_name)
    _require_mcp_client_ready(db, tenant)

    existing = db.scalar(select(RemoteMcpServer).where(RemoteMcpServer.server_key == payload.server_key))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Remote MCP server_key already exists")

    clean_token = payload.auth_token.strip() if payload.auth_token else None
    fingerprint = hashlib.sha256(clean_token.encode("utf-8")).hexdigest()[:32] if clean_token else None
    allowed = sorted({item.strip() for item in payload.allowed_tools if item.strip()})

    row = RemoteMcpServer(
        server_key=payload.server_key.strip(),
        name=payload.name.strip()[:160],
        base_url=safe_url,
        auth_header_name=payload.auth_header_name.strip()[:64],
        auth_token=encrypt_value(clean_token) if clean_token else None,
        auth_fingerprint=fingerprint,
        allowed_tools=allowed,
        discovered_tools=[],
        is_active=True,
        created_by=actor_user_id[:64] if actor_user_id else None,
        created_at=current,
        updated_at=current,
    )
    db.add(row)
    db.flush()
    create_system_event(
        db,
        "mcp_client.server.registered",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"server_id": row.id, "server_key": row.server_key, "allowed_tools": allowed},
    )
    db.commit()
    db.refresh(row)
    return _server_to_dict(row)


def revoke_remote_mcp_server(
    db: Session,
    tenant: TenantContext,
    server_id: int,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_mcp_client_ready(db, tenant)
    row = db.scalar(select(RemoteMcpServer).where(RemoteMcpServer.id == server_id).with_for_update())
    if row is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Remote MCP server not found")
    row.is_active = False
    row.revoked_at = row.revoked_at or current
    row.updated_at = current
    create_system_event(
        db,
        "mcp_client.server.revoked",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"server_id": row.id, "server_key": row.server_key, "actor_user_id": actor_user_id},
    )
    db.commit()
    db.refresh(row)
    return _server_to_dict(row)


def _auth_headers(server: RemoteMcpServer) -> dict[str, str]:
    if not server.auth_token:
        return {}
    token = decrypt_value(server.auth_token)
    if not token:
        return {}
    return {server.auth_header_name: token}


def discover_remote_mcp_tools(
    db: Session,
    tenant: TenantContext,
    server_id: int,
    *,
    transport: JsonRpcTransport | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_mcp_client_ready(db, tenant)
    row = db.scalar(select(RemoteMcpServer).where(RemoteMcpServer.id == server_id).with_for_update())
    if row is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Remote MCP server not found")
    if not row.is_active or row.revoked_at is not None:
        db.rollback()
        raise HTTPException(status_code=403, detail="Remote MCP server is revoked or inactive")
    if not is_external_ai_transfer_allowed_in_tx(db):
        create_system_event(
            db,
            "mcp_client.egress.blocked",
            tenant.auth_tenant_id,
            tenant.schema_name,
            {"server_id": row.id, "server_key": row.server_key, "action": "discover"},
        )
        db.commit()
        raise HTTPException(
            status_code=403,
            detail="External AI/MCP data transfer is disabled by tenant privacy policy",
        )

    _validate_webhook_url(row.base_url)
    sender = transport or _default_jsonrpc_transport
    rpc_res = sender(row.base_url, _auth_headers(row), {"jsonrpc": "2.0", "id": "discover-1", "method": "tools/list", "params": {}})
    if rpc_res.get("error"):
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Remote MCP error: {rpc_res['error']}")

    tools_raw = (rpc_res.get("result") or {}).get("tools") if isinstance(rpc_res.get("result"), dict) else []
    row.discovered_tools = list(tools_raw or [])
    row.updated_at = current
    db.commit()
    db.refresh(row)
    return _server_to_dict(row)


def invoke_remote_mcp_tool(
    db: Session,
    tenant: TenantContext,
    server_id: int,
    payload: RemoteMcpInvokeIn,
    *,
    actor_user_id: str,
    transport: JsonRpcTransport | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_mcp_client_ready(db, tenant)
    row = db.scalar(select(RemoteMcpServer).where(RemoteMcpServer.id == server_id).with_for_update())
    if row is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Remote MCP server not found")
    if not row.is_active or row.revoked_at is not None:
        db.rollback()
        raise HTTPException(status_code=403, detail="Remote MCP server is revoked or inactive")
    if not is_external_ai_transfer_allowed_in_tx(db):
        create_system_event(
            db,
            "mcp_client.egress.blocked",
            tenant.auth_tenant_id,
            tenant.schema_name,
            {
                "server_id": row.id,
                "server_key": row.server_key,
                "tool_name": payload.tool_name.strip(),
                "actor_user_id": actor_user_id,
                "action": "invoke",
            },
        )
        db.commit()
        raise HTTPException(
            status_code=403,
            detail="External AI/MCP data transfer is disabled by tenant privacy policy",
        )

    tool_name = payload.tool_name.strip()
    allowed_set = set(row.allowed_tools or [])
    if tool_name not in allowed_set:
        db.rollback()
        raise HTTPException(status_code=403, detail=f"Remote tool '{tool_name}' is not in server allowlist")

    audit_key = f"mcp:{row.server_key}:{tool_name}"[:80]
    idem_key = payload.idempotency_key.strip()[:180]
    canonical_args = json.dumps(payload.arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    args_hash = hashlib.sha256(canonical_args.encode("utf-8")).hexdigest()

    existing_inv = db.scalar(
        select(ToolInvocation).where(
            ToolInvocation.tool_key == audit_key,
            ToolInvocation.idempotency_key == idem_key,
        )
    )
    if existing_inv is not None:
        if existing_inv.arguments_hash != args_hash:
            db.rollback()
            raise HTTPException(status_code=409, detail="Idempotency-Key reused with different arguments")
        db.rollback()
        return {
            "invocation_id": existing_inv.id,
            "server_key": row.server_key,
            "tool_name": tool_name,
            "status": existing_inv.status,
            "duplicate": True,
            "result": dict(existing_inv.result_json or {}),
        }

    _validate_webhook_url(row.base_url)
    scrubbed_arguments, scrub_session = scrub_payload(dict(payload.arguments or {}))
    sender = transport or _default_jsonrpc_transport
    rpc_res = sender(
        row.base_url,
        {**_auth_headers(row), "Idempotency-Key": idem_key},
        {
            "jsonrpc": "2.0",
            "id": f"inv-{idem_key[:32]}",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": scrubbed_arguments},
        },
    )
    if rpc_res.get("error"):
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Remote MCP invocation failed: {rpc_res['error']}")

    db.execute(
        insert(ToolDefinition)
        .values(
            tool_key=audit_key,
            name=f"Remote MCP · {tool_name}"[:160],
            description=f"Remote MCP tool via {row.server_key}"[:400],
            effect_mode="external_mcp",
            schema_version=1,
            input_schema={"type": "object", "properties": {}},
            required_permission="crm.manage",
            connector_ref=f"mcp:{row.server_key}"[:80],
            is_enabled=True,
            max_calls_per_hour=240,
            created_by=actor_user_id[:64],
            created_at=current,
            updated_at=current,
        )
        .on_conflict_do_nothing(index_elements=["tool_key"])
    )
    tool_def = db.scalar(select(ToolDefinition).where(ToolDefinition.tool_key == audit_key))

    result_obj = dict(rpc_res.get("result") or {}) if isinstance(rpc_res.get("result"), dict) else {"raw": rpc_res}
    inv = ToolInvocation(
        tool_id=tool_def.id,
        tool_key=audit_key,
        schema_version=1,
        idempotency_key=idem_key,
        arguments_json=dict(payload.arguments or {}),
        arguments_hash=args_hash,
        effect_mode="external_mcp",
        status="completed",
        result_json=result_obj,
        invoked_by=actor_user_id[:64],
        created_at=current,
    )
    db.add(inv)
    db.flush()
    create_system_event(
        db,
        "mcp_client.tool.invoked",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"invocation_id": inv.id, "server_key": row.server_key, "tool_name": tool_name},
    )
    db.commit()
    db.refresh(inv)
    return {
        "invocation_id": inv.id,
        "server_key": row.server_key,
        "tool_name": tool_name,
        "status": inv.status,
        "duplicate": False,
        "result": result_obj,
    }
