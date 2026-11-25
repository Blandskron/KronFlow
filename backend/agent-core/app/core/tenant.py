from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from app.core.security import CurrentPrincipal, get_current_principal
from app.core.config import get_settings
from app.infrastructure.operational_context import operational_context_client


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str


def tenant_with_permission(permission: str):
    def dependency(request: Request, principal: CurrentPrincipal = Depends(get_current_principal)) -> TenantContext:
        local = not principal.raw_claims and "local" in principal.roles
        if permission not in principal.permissions and not local:
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        if get_settings().persistence_mode == "operational":
            if not principal.tenant_id.isascii() or not principal.tenant_id.isdecimal():
                raise HTTPException(status_code=403, detail="Invalid workspace")
            operational_context_client.require_active_workspace(principal.tenant_id)
        context = TenantContext(tenant_id=principal.tenant_id)
        request.state.tenant = context
        return context

    return dependency


resolve_tenant = tenant_with_permission("agents.create")
resolve_conversation_reader = tenant_with_permission("users.read")
resolve_audit_reader = tenant_with_permission("audit.read")
