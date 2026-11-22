from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.lead import LeadListResponse, LeadOut, LeadUpdate
from app.services.lead_service import get_lead, list_leads, update_lead

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

