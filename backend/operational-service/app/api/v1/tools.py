"""Governed tool catalog and idempotent tool invocation endpoints."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.tool_hub import (
    ToolCreateIn,
    ToolInvocationCreateIn,
    ToolInvocationOut,
    ToolOut,
    ToolUpdateIn,
)
from app.services.tool_hub_service import (
    create_tool,
    invoke_tool,
    list_tool_invocations,
    list_tools,
    update_tool,
)


router = APIRouter(prefix="/api/v1", tags=["Tools Hub"])


@router.get("/tools", response_model=list[ToolOut])
def list_tools_endpoint(
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return list_tools(db, tenant)


@router.post("/tools", response_model=ToolOut, status_code=status.HTTP_201_CREATED)
def create_tool_endpoint(
    payload: ToolCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return create_tool(db, tenant, payload, actor_user_id=principal.user_id)


@router.patch("/tools/{tool_id}", response_model=ToolOut)
def update_tool_endpoint(
    tool_id: int,
    payload: ToolUpdateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return update_tool(db, tenant, tool_id, payload)


@router.post("/tool-invocations", response_model=ToolInvocationOut)
def invoke_tool_endpoint(
    payload: ToolInvocationCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return invoke_tool(
        db,
        tenant,
        tool_key=payload.tool_key,
        arguments=payload.arguments,
        idempotency_key=payload.idempotency_key,
        actor_user_id=principal.user_id,
        expected_schema_version=payload.expected_schema_version,
    )


@router.get("/tool-invocations", response_model=list[ToolInvocationOut])
def list_tool_invocations_endpoint(
    tool_key: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return list_tool_invocations(db, tenant, tool_key=tool_key, limit=limit)
