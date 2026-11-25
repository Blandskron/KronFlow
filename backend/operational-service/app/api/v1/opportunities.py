from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.opportunity import (
    OpportunityActivityCreateIn,
    OpportunityActivityOut,
    OpportunityCreateIn,
    OpportunityListResponse,
    OpportunityOut,
    OpportunityUpdateIn,
    PipelineStageCreateIn,
    PipelineStageListResponse,
    PipelineStageOut,
)
from app.services.opportunity_service import (
    _UNSET,
    add_opportunity_activity,
    create_opportunity,
    create_pipeline_stage,
    get_opportunity,
    list_opportunities,
    list_pipeline_stages,
    update_opportunity,
)


router = APIRouter(prefix="/api/v1/opportunities", tags=["Opportunities"])


@router.get("/stages", response_model=PipelineStageListResponse)
def stages_list(
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return PipelineStageListResponse(items=list_pipeline_stages(db, tenant))


@router.post("/stages", response_model=PipelineStageOut, status_code=status.HTTP_201_CREATED)
def stages_create(
    payload: PipelineStageCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return create_pipeline_stage(
        db,
        tenant,
        slug=payload.slug,
        name=payload.name,
        position=payload.position,
        stage_kind=payload.stage_kind,
    )


@router.get("", response_model=OpportunityListResponse)
def opportunities_list(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    stage_id: int | None = Query(default=None, ge=1),
    owner_user_id: str | None = Query(default=None, max_length=64),
    outcome: Literal["open", "won", "lost"] | None = None,
    contact_id: int | None = Query(default=None, ge=1),
    lead_id: int | None = Query(default=None, ge=1),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    limit = min(limit, settings.max_page_size)
    items, total = list_opportunities(
        db,
        tenant,
        limit=limit,
        offset=offset,
        stage_id=stage_id,
        owner_user_id=owner_user_id,
        outcome=outcome,
        contact_id=contact_id,
        lead_id=lead_id,
    )
    return OpportunityListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=OpportunityOut, status_code=status.HTTP_201_CREATED)
def opportunities_create(
    payload: OpportunityCreateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return create_opportunity(
        db,
        tenant,
        title=payload.title,
        contact_id=payload.contact_id,
        lead_id=payload.lead_id,
        conversation_id=payload.conversation_id,
        stage_id=payload.stage_id,
        owner_user_id=payload.owner_user_id,
        amount=payload.amount,
        currency=payload.currency,
        actor_user_id=principal.user_id,
    )


@router.get("/{opportunity_id}", response_model=OpportunityOut)
def opportunities_get(
    opportunity_id: int,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return get_opportunity(db, tenant, opportunity_id)


@router.patch("/{opportunity_id}", response_model=OpportunityOut)
def opportunities_update(
    opportunity_id: int,
    payload: OpportunityUpdateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    fields = payload.model_fields_set
    return update_opportunity(
        db,
        tenant,
        opportunity_id,
        expected_version=payload.expected_version,
        actor_user_id=principal.user_id,
        title=payload.title if "title" in fields else None,
        stage_id=payload.stage_id if "stage_id" in fields else None,
        owner_user_id=payload.owner_user_id if "owner_user_id" in fields else _UNSET,
        amount=payload.amount if "amount" in fields else _UNSET,
        currency=payload.currency if "currency" in fields else None,
        outcome=payload.outcome if "outcome" in fields else None,
        close_reason=payload.close_reason if "close_reason" in fields else None,
        note=payload.note if "note" in fields else None,
    )


@router.post("/{opportunity_id}/activities", response_model=OpportunityActivityOut, status_code=status.HTTP_201_CREATED)
def opportunities_add_activity(
    opportunity_id: int,
    payload: OpportunityActivityCreateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return add_opportunity_activity(
        db,
        tenant,
        opportunity_id,
        actor_user_id=principal.user_id,
        note=payload.note,
    )
