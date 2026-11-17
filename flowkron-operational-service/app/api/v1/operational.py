from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.tenant_resolver import TenantContext, resolve_audit_reader, resolve_tenant_from_jwt
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

router = APIRouter(prefix="/api/v1/operational", tags=["Operational Data"])


def page_size(limit: int, settings: Settings) -> int:
    return min(limit, settings.max_page_size)


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
