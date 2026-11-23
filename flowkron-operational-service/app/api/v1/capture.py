from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor
from app.schemas.capture import (
    BackfillContactPointsOut,
    LeadCaptureAcceptedOut,
    LeadCaptureIn,
    PublicFormCreateIn,
    PublicFormOut,
    ScopedCredentialCreateIn,
    ScopedCredentialOut,
)
from app.services.capture_service import (
    authenticate_scoped_credential,
    backfill_contact_points,
    capture_lead,
    create_public_form,
    issue_scoped_credential,
    resolve_public_form,
    revoke_scoped_credential,
)


router = APIRouter(prefix="/api/v1", tags=["Capture & Credentials"])


@router.post("/contacts/backfill-points", response_model=BackfillContactPointsOut)
def backfill_points_endpoint(
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return backfill_contact_points(db, tenant)


@router.post("/integrations/credentials", response_model=ScopedCredentialOut, status_code=status.HTTP_201_CREATED)
def issue_credential_endpoint(
    payload: ScopedCredentialCreateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return issue_scoped_credential(
        db,
        tenant,
        name=payload.name,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
        created_by=principal.user_id,
    )


@router.post("/integrations/credentials/{credential_id}/revoke", response_model=ScopedCredentialOut)
def revoke_credential_endpoint(
    credential_id: int,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return revoke_scoped_credential(db, tenant, credential_id)


@router.post("/integrations/leads", response_model=LeadCaptureAcceptedOut, status_code=status.HTTP_202_ACCEPTED)
def capture_integration_lead(
    payload: LeadCaptureIn,
    x_flowkron_key: str | None = Header(default=None, alias="X-Flowkron-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=422, detail="Idempotency-Key header is required")
    tenant, cred = authenticate_scoped_credential(db, x_flowkron_key, required_scope="leads:create")
    return capture_lead(
        db,
        tenant,
        source_kind="integration",
        source_ref=cred.key_prefix,
        idempotency_key=idempotency_key,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        message=payload.message,
        marketing_opt_in=payload.marketing_opt_in,
    )


@router.post("/forms", response_model=PublicFormOut, status_code=status.HTTP_201_CREATED)
def create_form_endpoint(
    payload: PublicFormCreateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return create_public_form(
        db,
        tenant,
        name=payload.name,
        source_label=payload.source_label,
        allowed_fields=payload.allowed_fields,
        created_by=principal.user_id,
    )


@router.post("/forms/{form_token}/submissions", response_model=LeadCaptureAcceptedOut, status_code=status.HTTP_202_ACCEPTED)
def submit_public_form(
    form_token: str,
    payload: LeadCaptureIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    tenant, form = resolve_public_form(db, form_token)
    key = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else f"pub:{uuid4().hex}"
    return capture_lead(
        db,
        tenant,
        source_kind="public_form",
        source_ref=str(form.id),
        idempotency_key=key,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        message=payload.message,
        marketing_opt_in=payload.marketing_opt_in,
        honeypot=payload.website,
    )
