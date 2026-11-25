from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.ai_proposal import (
    AIProposalCreateIn,
    AIProposalExecuteIn,
    AIProposalListResponse,
    AIProposalOut,
    AIProposalReviewIn,
)
from app.services.ai_proposal_service import (
    create_ai_proposal,
    execute_ai_proposal,
    get_ai_proposal,
    list_ai_proposals,
    review_ai_proposal,
)


router = APIRouter(prefix="/api/v1/ai-proposals", tags=["AI Proposals"])


@router.get("", response_model=AIProposalListResponse)
def proposals_list(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    status_filter: Literal["pending", "approved", "rejected", "executed", "expired"] | None = Query(default=None, alias="status"),
    resource_type: Literal["contact", "lead", "opportunity", "conversation"] | None = None,
    resource_id: int | None = Query(default=None, ge=1),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    limit = min(limit, settings.max_page_size)
    items, total = list_ai_proposals(
        db,
        tenant,
        limit=limit,
        offset=offset,
        status_filter=status_filter,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    return AIProposalListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=AIProposalOut, status_code=status.HTTP_201_CREATED)
def proposals_create(
    payload: AIProposalCreateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return create_ai_proposal(
        db,
        tenant,
        action_type=payload.action_type,
        resource_id=payload.resource_id,
        arguments=payload.arguments,
        idempotency_key=payload.idempotency_key,
        proposed_by=principal.user_id,
        rationale=payload.rationale,
        expires_at=payload.expires_at,
    )


@router.get("/{proposal_id}", response_model=AIProposalOut)
def proposals_get(
    proposal_id: int,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return get_ai_proposal(db, tenant, proposal_id)


@router.post("/{proposal_id}/approve", response_model=AIProposalOut)
def proposals_approve(
    proposal_id: int,
    payload: AIProposalReviewIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return review_ai_proposal(
        db,
        tenant,
        proposal_id,
        decision="approved",
        expected_version=payload.expected_version,
        reviewer_user_id=principal.user_id,
        review_note=payload.review_note,
    )


@router.post("/{proposal_id}/reject", response_model=AIProposalOut)
def proposals_reject(
    proposal_id: int,
    payload: AIProposalReviewIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return review_ai_proposal(
        db,
        tenant,
        proposal_id,
        decision="rejected",
        expected_version=payload.expected_version,
        reviewer_user_id=principal.user_id,
        review_note=payload.review_note,
    )


@router.post("/{proposal_id}/execute", response_model=AIProposalOut)
def proposals_execute(
    proposal_id: int,
    payload: AIProposalExecuteIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return execute_ai_proposal(
        db,
        tenant,
        proposal_id,
        executor_user_id=principal.user_id,
        expected_version=payload.expected_version,
    )
