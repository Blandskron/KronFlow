from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_agent_editor
from app.schemas.agent import (
    AgentConfigureRequest,
    AgentOut,
    AgentPublishRequest,
    AgentRevisionOut,
    AgentRollbackRequest,
    AgentUpdateRequest,
)
from app.services.agent_service import (
    configure_agent,
    get_agent,
    list_agent_revisions,
    list_agents,
    publish_agent,
    rollback_agent,
    update_agent,
)

router = APIRouter(prefix="/api/v1/agents", tags=["Agents"])


@router.get("", response_model=list[AgentOut])
def list_endpoint(tenant: TenantContext = Depends(resolve_agent_editor), db: Session = Depends(get_db)):
    return list_agents(db, tenant)


@router.get("/{agent_id}", response_model=AgentOut)
def get_endpoint(agent_id: int, tenant: TenantContext = Depends(resolve_agent_editor), db: Session = Depends(get_db)):
    agent = get_agent(db, tenant, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@router.post("/configure", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def configure(
    payload: AgentConfigureRequest,
    principal: CurrentPrincipal = Depends(require_permission("agents.create")),
    tenant: TenantContext = Depends(resolve_agent_editor),
    db: Session = Depends(get_db),
):
    return configure_agent(db, tenant, payload, actor_user_id=principal.user_id)


@router.patch("/{agent_id}", response_model=AgentOut)
def update(
    agent_id: int,
    payload: AgentUpdateRequest,
    principal: CurrentPrincipal = Depends(require_permission("agents.create")),
    tenant: TenantContext = Depends(resolve_agent_editor),
    db: Session = Depends(get_db),
):
    agent = update_agent(db, tenant, agent_id, payload, actor_user_id=principal.user_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@router.post("/{agent_id}/publish", response_model=AgentRevisionOut, status_code=status.HTTP_201_CREATED)
def publish_endpoint(
    agent_id: int,
    payload: AgentPublishRequest,
    principal: CurrentPrincipal = Depends(require_permission("agents.create")),
    tenant: TenantContext = Depends(resolve_agent_editor),
    db: Session = Depends(get_db),
):
    return publish_agent(
        db,
        tenant,
        agent_id,
        expected_version=payload.expected_version,
        actor_user_id=principal.user_id,
        note=payload.note,
    )


@router.get("/{agent_id}/revisions", response_model=list[AgentRevisionOut])
def revisions_endpoint(
    agent_id: int,
    tenant: TenantContext = Depends(resolve_agent_editor),
    db: Session = Depends(get_db),
):
    return list_agent_revisions(db, tenant, agent_id)


@router.post("/{agent_id}/rollback", response_model=AgentOut)
def rollback_endpoint(
    agent_id: int,
    payload: AgentRollbackRequest,
    principal: CurrentPrincipal = Depends(require_permission("agents.create")),
    tenant: TenantContext = Depends(resolve_agent_editor),
    db: Session = Depends(get_db),
):
    return rollback_agent(
        db,
        tenant,
        agent_id,
        expected_version=payload.expected_version,
        revision_id=payload.revision_id,
        actor_user_id=principal.user_id,
    )
