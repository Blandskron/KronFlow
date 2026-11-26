"""API routes for tenant-scoped approved remote MCP servers (client side)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.mcp_client import RemoteMcpInvokeIn, RemoteMcpServerCreateIn
from app.services.mcp_client_service import (
    discover_remote_mcp_tools,
    invoke_remote_mcp_tool,
    list_remote_mcp_servers,
    register_remote_mcp_server,
    revoke_remote_mcp_server,
)


router = APIRouter(prefix="/api/v1/mcp-clients", tags=["Remote MCP Clients"])


@router.get("")
def list_remote_mcp_servers_endpoint(
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    _principal: CurrentPrincipal = Depends(require_permission("users.read")),
    db: Session = Depends(get_db),
):
    return list_remote_mcp_servers(db, tenant)


@router.post("")
def register_remote_mcp_server_endpoint(
    payload: RemoteMcpServerCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return register_remote_mcp_server(db, tenant, payload, actor_user_id=principal.user_id)


@router.post("/{server_id}/discover")
def discover_remote_mcp_tools_endpoint(
    server_id: int,
    tenant: TenantContext = Depends(resolve_crm_editor),
    _principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return discover_remote_mcp_tools(db, tenant, server_id)


@router.post("/{server_id}/invoke")
def invoke_remote_mcp_tool_endpoint(
    server_id: int,
    payload: RemoteMcpInvokeIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return invoke_remote_mcp_tool(db, tenant, server_id, payload, actor_user_id=principal.user_id)


@router.post("/{server_id}/revoke")
def revoke_remote_mcp_server_endpoint(
    server_id: int,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return revoke_remote_mcp_server(db, tenant, server_id, actor_user_id=principal.user_id)
