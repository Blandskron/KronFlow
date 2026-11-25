import hmac
import re
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.admission import admit_ingest_request
from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission, verify_secret
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


def _resolve_tenant(request: Request, principal: CurrentPrincipal, db: Session) -> TenantContext:
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


def tenant_with_permission(permission: str):
    def dependency(
        request: Request,
        principal: CurrentPrincipal = Depends(require_permission(permission)),
        db: Session = Depends(get_db),
    ) -> TenantContext:
        return _resolve_tenant(request, principal, db)

    return dependency


resolve_tenant_from_jwt = tenant_with_permission("users.read")
resolve_crm_editor = tenant_with_permission("crm.manage")
resolve_agent_editor = tenant_with_permission("agents.create")
resolve_audit_reader = tenant_with_permission("audit.read")


def resolve_tenant_from_ingest_headers(
    request: Request,
    x_tenant_code: str | None = Header(default=None, alias="X-Tenant-Code"),
    x_ingest_key: str | None = Header(default=None, alias="X-Ingest-Key"),
    bridge_tenant: int | None = Header(default=None, alias="X-Flowkron-Tenant"),
    bridge_token: str | None = Header(default=None, alias="X-Baileys-Token"),
    db: Session = Depends(get_db),
) -> TenantContext:
    if not getattr(request.state, "ingest_admitted", False):
        admit_ingest_request(request)
    if bridge_tenant is not None or bridge_token is not None:
        expected = get_settings().baileys_internal_token
        if not expected or not bridge_token or not bridge_tenant or not hmac.compare_digest(expected.encode(), bridge_token.encode()):
            raise HTTPException(status_code=401, detail="Invalid Baileys credentials")
        runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == bridge_tenant))
        if not runtime:
            raise HTTPException(status_code=404, detail="Tenant runtime not provisioned")
        ensure_runtime_is_usable(runtime)
        context = TenantContext(runtime.auth_tenant_id, runtime.tenant_slug, runtime.schema_name, runtime.tenant_code, runtime.plan, runtime.status)
        request.state.tenant = context
        return context
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
