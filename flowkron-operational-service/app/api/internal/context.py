from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_internal_token
from app.core.tenant_resolver import TenantContext, ensure_runtime_is_usable
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.context import (
    BusinessContextStatusRead,
    ContextDocumentCreate,
    ContextDocumentRead,
    ContextRetrieveRequest,
    ContextSourceRead,
)
from app.services.context_service import create_context_document, context_status, list_context_documents, retrieve_context_sources


router = APIRouter(prefix="/internal/tenants/{tenant_id}/context", tags=["Internal Context"], dependencies=[Depends(require_internal_token)])


def resolve_internal_tenant(tenant_id: int, db: Session) -> TenantContext:
    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == tenant_id))
    if not runtime:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant runtime not provisioned")
    ensure_runtime_is_usable(runtime)
    return TenantContext(
        auth_tenant_id=runtime.auth_tenant_id,
        tenant_slug=runtime.tenant_slug,
        schema_name=runtime.schema_name,
        tenant_code=runtime.tenant_code,
        plan=runtime.plan,
        status=runtime.status,
    )


@router.post("/documents", response_model=ContextDocumentRead, status_code=status.HTTP_201_CREATED)
def create_document(tenant_id: int, payload: ContextDocumentCreate, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return create_context_document(db, tenant, payload)


@router.get("/documents", response_model=list[ContextDocumentRead])
def list_documents(tenant_id: int, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return list_context_documents(db, tenant)


@router.get("/status", response_model=BusinessContextStatusRead)
def get_status(tenant_id: int, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return context_status(db, tenant)


@router.post("/retrieve", response_model=list[ContextSourceRead])
def retrieve(tenant_id: int, payload: ContextRetrieveRequest, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return retrieve_context_sources(db, tenant, payload.query, payload.limit)
