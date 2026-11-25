from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas.rules import RuleCreate, RulePatch, RuleRead
from app.core.config import get_settings
from app.core.database import get_db
from app.core.tenant import TenantContext, resolve_tenant
from app.models.agent import AgentRule

router = APIRouter(prefix="/api/v1/agent/rules", tags=["Agent Rules"])


def require_local_persistence() -> None:
    if get_settings().persistence_mode == "operational":
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Rules persistence is delegated to flowkron-operational-service.")


@router.get("", response_model=list[RuleRead])
def list_rules(tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    return db.scalars(select(AgentRule).where(AgentRule.tenant_id == tenant.tenant_id).order_by(AgentRule.priority)).all()


@router.post("", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(payload: RuleCreate, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    rule = AgentRule(tenant_id=tenant.tenant_id, **payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=RuleRead)
def patch_rule(rule_id: int, payload: RulePatch, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    rule = db.get(AgentRule, rule_id)
    if not rule or rule.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    rule = db.get(AgentRule, rule_id)
    if not rule or rule.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
