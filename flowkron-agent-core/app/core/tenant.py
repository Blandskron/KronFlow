from dataclasses import dataclass

from fastapi import Depends, Request

from app.core.security import CurrentPrincipal, get_current_principal


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str


def resolve_tenant(
    request: Request,
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> TenantContext:
    context = TenantContext(tenant_id=principal.tenant_id)
    request.state.tenant = context
    return context
