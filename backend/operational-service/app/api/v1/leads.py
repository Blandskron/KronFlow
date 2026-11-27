from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_audit_reader, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.lead import LeadActivityItem, LeadListResponse, LeadOut, LeadUpdate
from app.services.lead_service import get_lead, list_lead_activity, list_leads, update_lead
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.services.workflow_cancellation import cancel_waiting_runs_in_tx
from app.tenant_models.operations import Lead


class LeadHumanReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = "automated_decision_contested"

router = APIRouter(prefix="/api/v1/leads", tags=["Leads"])


@router.get("", response_model=LeadListResponse)
def list_endpoint(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    temperature: str | None = None,
    lifecycle_status: str | None = None,
    direction: str | None = None,
    q: str | None = Query(default=None, max_length=120),
    contact_id: int | None = Query(default=None, ge=1, le=9223372036854775807),
    status_group: Literal["open", "closed"] | None = None,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    limit = min(limit, settings.max_page_size)
    items, total = list_leads(
        db, tenant, limit, offset, temperature, lifecycle_status, direction,
        search=q, contact_id=contact_id, status_group=status_group,
    )
    return LeadListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{lead_id}", response_model=LeadOut)
def retrieve(lead_id: int, tenant: TenantContext = Depends(resolve_tenant_from_jwt), db: Session = Depends(get_db)):
    lead = get_lead(db, tenant, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadOut)
def update(lead_id: int, payload: LeadUpdate, tenant: TenantContext = Depends(resolve_crm_editor), db: Session = Depends(get_db)):
    lead = update_lead(db, tenant, lead_id, payload)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


@router.get("/{lead_id}/activity", response_model=list[LeadActivityItem])
def activity(
    lead_id: int = Path(ge=1, le=9223372036854775807),
    limit: int = Query(default=25, ge=1, le=50),
    tenant: TenantContext = Depends(resolve_audit_reader), db: Session = Depends(get_db),
):
    return list_lead_activity(db, tenant, lead_id, limit)


@router.get("/{lead_id}/score-explanation")
def score_explanation(
    lead_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    """Explain automated lead scoring factors and human review status (GDPR Art. 22 / Ley 21.719 Art. 8 bis, PRV-016)."""
    bind_tenant_session(db, tenant.schema_name)
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return {
        "lead_id": lead.id,
        "score_lead": lead.score_lead,
        "clasificacion": lead.clasificacion,
        "score_factors": dict(lead.score_factors_json or {}),
        "human_review_requested": bool(lead.human_review_requested),
        "human_review_reason": lead.human_review_reason,
    }


@router.post("/{lead_id}/human-review")
def request_lead_human_review(
    payload: LeadHumanReviewIn,
    lead_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    """Mark a lead as contested for human review and pause waiting automations (PRV-016)."""
    now = datetime.now(UTC)
    bind_tenant_session(db, tenant.schema_name)
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    lead.human_review_requested = True
    lead.human_review_reason = payload.reason.strip()[:240] or "automated_decision_contested"
    lead.estado_seguimiento = "requiere_humano"
    cancelled = cancel_waiting_runs_in_tx(
        db,
        tenant,
        event_type="lead.human_review.requested",
        contact_id=lead.cliente_id,
        reason="human_review_requested",
        now=now,
    )
    create_system_event(
        db,
        "lead.human_review.requested",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {
            "lead_id": lead.id,
            "contact_id": lead.cliente_id,
            "reason": lead.human_review_reason,
            "workflow_runs_cancelled": cancelled,
            "actor_id": principal.user_id,
        },
    )
    db.commit()
    return {
        "lead_id": lead.id,
        "human_review_requested": True,
        "human_review_reason": lead.human_review_reason,
        "workflow_runs_cancelled": cancelled,
    }

