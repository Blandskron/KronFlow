from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_resolver import TenantContext, resolve_agent_editor
from app.schemas.agent import AgentConfigureRequest, AgentOut, AgentUpdateRequest
from app.services.agent_service import configure_agent, list_agents, update_agent

router = APIRouter(prefix="/api/v1/agents", tags=["Agents"])


@router.get("", response_model=list[AgentOut])
def list_endpoint(tenant: TenantContext = Depends(resolve_agent_editor), db: Session = Depends(get_db)):
    return list_agents(db, tenant)


@router.post("/configure", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def configure(payload: AgentConfigureRequest, tenant: TenantContext = Depends(resolve_agent_editor), db: Session = Depends(get_db)):
    return configure_agent(db, tenant, payload)


@router.patch("/{agent_id}", response_model=AgentOut)
def update(agent_id: int, payload: AgentUpdateRequest, tenant: TenantContext = Depends(resolve_agent_editor), db: Session = Depends(get_db)):
    agent = update_agent(db, tenant, agent_id, payload)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent
