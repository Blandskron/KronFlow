from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_audit_reader, resolve_tenant_from_jwt
from app.schemas.audit_event import AuditEventPage
from app.schemas.privacy_case import (
    CaseState,
    PrivacyCaseExportOut,
    PrivacyCaseOut,
    PrivacyCasePage,
    PrivacyCaseTransition,
    PrivacyErasureIn,
    PrivacyErasureOut,
    RetentionSweepIn,
    RetentionSweepOut,
)
from app.services.operational_read_service import (
    list_clientes,
    list_conversaciones,
    list_ejecutivos,
    list_inventario,
    list_leads_operational,
    list_log_limpiezas,
    list_mensajes_dashboard,
    list_solicitudes_derechos,
)
from app.services.privacy_case_service import (
    execute_privacy_erasure,
    export_privacy_case_data,
    list_privacy_cases,
    run_retention_sweep,
    transition_privacy_case,
)
from app.services.audit_event_service import list_audit_events

router = APIRouter(prefix="/api/v1/operational", tags=["Operational Data"])


def page_size(limit: int, settings: Settings) -> int:
    return min(limit, settings.max_page_size)


@router.get("/audit-events", response_model=AuditEventPage)
def audit_events(
    limit: int = Query(default=25, ge=1, le=50),
    before_id: int | None = Query(default=None, ge=1, le=2147483647),
    event_type: str | None = Query(default=None, max_length=80),
    correlation_id: UUID | None = None,
    tenant: TenantContext = Depends(resolve_audit_reader), db: Session = Depends(get_db),
):
    return list_audit_events(db, tenant, limit, before_id, event_type, correlation_id)


@router.get("/clientes")
def clientes(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_clientes(db, tenant, page_size(limit, settings), offset)


@router.get("/leads")
def leads(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_leads_operational(db, tenant, page_size(limit, settings), offset)


@router.get("/inventario-vehiculos")
def inventario_vehiculos(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    disponible: bool | None = None,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_inventario(db, tenant, page_size(limit, settings), offset, disponible)


@router.get("/conversaciones")
def conversaciones(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_conversaciones(db, tenant, page_size(limit, settings), offset)


@router.get("/mensajes-dashboard")
def mensajes_dashboard(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    whatsapp_id: str | None = None,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_mensajes_dashboard(db, tenant, page_size(limit, settings), offset, whatsapp_id)


@router.get("/solicitudes-derechos")
def solicitudes_derechos(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_solicitudes_derechos(db, tenant, page_size(limit, settings), offset)


@router.get("/privacy-cases", response_model=PrivacyCasePage)
def privacy_cases(
    state: CaseState | None = None,
    limit: int = Query(default=25, ge=1, le=50), offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_audit_reader), db: Session = Depends(get_db),
):
    return list_privacy_cases(db, tenant, state, limit, offset)


@router.patch("/privacy-cases/{case_id}", response_model=PrivacyCaseOut)
def change_privacy_case(
    transition: PrivacyCaseTransition,
    case_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_audit_reader), db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return transition_privacy_case(db, tenant, case_id, transition, principal.user_id)


@router.post("/privacy-cases/{case_id}/export", response_model=PrivacyCaseExportOut)
def export_privacy_case(
    case_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return export_privacy_case_data(db, tenant, case_id, actor_id=principal.user_id)


@router.post("/privacy-cases/{case_id}/erase", response_model=PrivacyErasureOut)
def erase_privacy_case(
    payload: PrivacyErasureIn,
    case_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return execute_privacy_erasure(db, tenant, case_id, actor_id=principal.user_id, confirmed=payload.confirmed)


@router.post("/retention/sweep", response_model=RetentionSweepOut)
def retention_sweep(
    payload: RetentionSweepIn,
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return run_retention_sweep(
        db, tenant, message_retention_days=payload.message_retention_days, actor_id=principal.user_id,
    )


@router.get("/ejecutivos")
def ejecutivos(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_ejecutivos(db, tenant, page_size(limit, settings), offset)


@router.get("/log-limpiezas")
def log_limpiezas(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_log_limpiezas(db, tenant, page_size(limit, settings), offset)
