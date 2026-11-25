from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.agent import AgentConfigureRequest, AgentUpdateRequest


def list_agents(db: Session, tenant: TenantContext) -> list[dict]:
    return []


def configure_agent(db: Session, tenant: TenantContext, payload: AgentConfigureRequest) -> dict:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Agent configuration storage is not part of the current tenant schema yet",
    )


def update_agent(db: Session, tenant: TenantContext, agent_id: int, payload: AgentUpdateRequest) -> dict | None:
    return None
