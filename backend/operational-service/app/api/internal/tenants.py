from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_internal_token
from app.core.tenant_resolver import TenantContext, ensure_runtime_is_usable
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.tenant import RotateIngestKeyResponse, TenantProvisionRequest, TenantProvisionResponse, TenantRuntimeResponse
from app.services.demo_seed_service import seed_demo_tenant_data
from app.services.tenant_provisioning_service import provision_tenant, rotate_ingest_key, set_tenant_status

router = APIRouter(prefix="/internal/tenants", tags=["Internal Tenants"], dependencies=[Depends(require_internal_token)])


@router.post("/provision", response_model=TenantProvisionResponse, status_code=status.HTTP_201_CREATED)
def provision(request: TenantProvisionRequest, db: Session = Depends(get_db)):
    runtime, ingest_key, created = provision_tenant(db, request)
    return TenantProvisionResponse(runtime=runtime, ingest_key=ingest_key, created=created)


@router.get("/{tenant_id}/runtime", response_model=TenantRuntimeResponse)
def get_runtime(tenant_id: int, db: Session = Depends(get_db)):
    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == tenant_id))
    if not runtime:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant runtime not found")
    return runtime


@router.post("/{tenant_id}/suspend", response_model=TenantRuntimeResponse)
def suspend(tenant_id: int, db: Session = Depends(get_db)):
    runtime = set_tenant_status(db, tenant_id, "suspended")
    if not runtime:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant runtime not found")
    return runtime


@router.post("/{tenant_id}/activate", response_model=TenantRuntimeResponse)
def activate(tenant_id: int, db: Session = Depends(get_db)):
    runtime = set_tenant_status(db, tenant_id, "active")
    if not runtime:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant runtime not found")
    return runtime


@router.post("/{tenant_id}/rotate-ingest-key", response_model=RotateIngestKeyResponse)
def rotate_key(tenant_id: int, db: Session = Depends(get_db)):
    runtime, ingest_key = rotate_ingest_key(db, tenant_id)
    if not runtime or not ingest_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant runtime not found")
    return RotateIngestKeyResponse(tenant_code=runtime.tenant_code, ingest_key=ingest_key)


@router.post("/{tenant_id}/demo-seed")
def seed_demo_data(tenant_id: int, db: Session = Depends(get_db)):
    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == tenant_id))
    if not runtime:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant runtime not found")
    ensure_runtime_is_usable(runtime)
    tenant = TenantContext(
        auth_tenant_id=runtime.auth_tenant_id,
        tenant_slug=runtime.tenant_slug,
        schema_name=runtime.schema_name,
        tenant_code=runtime.tenant_code,
        plan=runtime.plan,
        status=runtime.status,
    )
    return seed_demo_tenant_data(db, tenant)

