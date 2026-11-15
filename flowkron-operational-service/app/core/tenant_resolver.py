import re
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, get_current_principal, verify_secret
from app.public_models.tenant_runtime import TenantRuntime

SCHEMA_NAME_RE = re.compile(r"[^a-z0-9_]+")


def sanitize_schema_name(value: str) -> str:
    normalized = SCHEMA_NAME_RE.sub("_", value.strip().lower()).strip("_")
    normalized = re.sub(r"_+", "_", normalized)
    if not normalized:
        normalized = "tenant"
    if not normalized.startswith("tenant_"):
        normalized = f"tenant_{normalized}"
    return normalized[:63]


def quote_identifier(identifier: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", identifier):
        raise ValueError("Invalid PostgreSQL identifier")
    return f'"{identifier}"'


@dataclass(frozen=True)
class TenantContext:
    auth_tenant_id: int
    tenant_slug: str
    schema_name: str
    tenant_code: str
    plan: str
    status: str


def ensure_runtime_is_usable(runtime: TenantRuntime) -> None:
    if runtime.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant is not active")
    if runtime.plan in {"free", ""}:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Tenant requires an active paid plan")


def resolve_tenant_from_jwt(
    request: Request,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> TenantContext:
    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == principal.tenant_id))
    if not runtime:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant runtime not provisioned")
    ensure_runtime_is_usable(runtime)
    context = TenantContext(
        auth_tenant_id=runtime.auth_tenant_id,
        tenant_slug=runtime.tenant_slug,
        schema_name=runtime.schema_name,
        tenant_code=runtime.tenant_code,
        plan=runtime.plan,
        status=runtime.status,
    )
    request.state.tenant = context
    return context


def resolve_tenant_from_ingest_headers(
    request: Request,
    x_tenant_code: str | None = Header(default=None, alias="X-Tenant-Code"),
    x_ingest_key: str | None = Header(default=None, alias="X-Ingest-Key"),
    db: Session = Depends(get_db),
) -> TenantContext:
    if not x_tenant_code or not x_ingest_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing ingest credentials")

    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.tenant_code == x_tenant_code))
    if not runtime or not verify_secret(x_ingest_key, runtime.ingest_key_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ingest credentials")
    ensure_runtime_is_usable(runtime)
    context = TenantContext(
        auth_tenant_id=runtime.auth_tenant_id,
        tenant_slug=runtime.tenant_slug,
        schema_name=runtime.schema_name,
        tenant_code=runtime.tenant_code,
        plan=runtime.plan,
        status=runtime.status,
    )
    request.state.tenant = context
    return context
