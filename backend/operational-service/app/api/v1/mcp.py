"""Governed MCP JSON-RPC 2.0 endpoint authenticated via scoped key or CRM manager JWT."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import get_current_principal
from app.core.tenant_resolver import TenantContext, ensure_runtime_is_usable
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.mcp import JsonRpcRequestIn, JsonRpcResponseOut
from app.services.capture_service import authenticate_scoped_credential
from app.services.mcp_service import handle_mcp_request


router = APIRouter(prefix="/api/v1", tags=["MCP Server"])


@router.post("/mcp", response_model=JsonRpcResponseOut)
def mcp_jsonrpc_endpoint(
    rpc_req: JsonRpcRequestIn,
    request: Request,
    x_flowkron_key: str | None = Header(default=None, alias="X-Flowkron-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    method = rpc_req.method.strip()
    if x_flowkron_key:
        required = "mcp:invoke" if method == "tools/call" else "mcp:read"
        tenant, cred = authenticate_scoped_credential(db, x_flowkron_key, required_scope=required)
        return handle_mcp_request(
            db,
            tenant,
            rpc_req,
            actor_user_id=f"cred:{cred.key_prefix}",
            allowed_scopes=set(cred.scopes or []),
            header_idempotency_key=idempotency_key,
        )

    override = request.app.dependency_overrides.get(get_current_principal)
    principal = override() if override is not None else get_current_principal(request, authorization, settings)
    if not principal.has_permission("crm.manage"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing permission: crm.manage")
    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == principal.tenant_id))
    if not runtime:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant runtime not provisioned")
    ensure_runtime_is_usable(runtime)
    tenant = TenantContext(
        auth_tenant_id=runtime.auth_tenant_id,
        tenant_slug=runtime.tenant_slug,
        schema_name=runtime.schema_name,
        tenant_code=runtime.tenant_code,
        plan=runtime.plan,
        status=runtime.status,
    )
    return handle_mcp_request(
        db,
        tenant,
        rpc_req,
        actor_user_id=principal.user_id,
        allowed_scopes=None,
        header_idempotency_key=idempotency_key,
    )
