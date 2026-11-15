from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.services.tenant_data import count_for_tenant, execute_for_tenant
from app.tenant_models.operations import Cliente, Conversation, Ejecutivo, InventarioVehiculo, Lead, LogLimpieza, Message, SolicitudDerecho


def model_to_dict(item: Any) -> dict[str, Any]:
    return {column.name: getattr(item, column.name) for column in item.__table__.columns}


def list_records(db: Session, tenant: TenantContext, statement: Select, limit: int, offset: int) -> dict[str, Any]:
    total = count_for_tenant(db, tenant.schema_name, statement)
    items = execute_for_tenant(db, tenant.schema_name, statement.limit(limit).offset(offset)).scalars().all()
    return {"items": [model_to_dict(item) for item in items], "total": total, "limit": limit, "offset": offset}


def list_clientes(db: Session, tenant: TenantContext, limit: int, offset: int) -> dict[str, Any]:
    return list_records(db, tenant, select(Cliente).order_by(Cliente.creado_en.desc()), limit, offset)


def list_leads_operational(db: Session, tenant: TenantContext, limit: int, offset: int) -> dict[str, Any]:
    return list_records(db, tenant, select(Lead).order_by(Lead.actualizado_en.desc()), limit, offset)


def list_inventario(db: Session, tenant: TenantContext, limit: int, offset: int, disponible: bool | None = None) -> dict[str, Any]:
    statement = select(InventarioVehiculo).order_by(InventarioVehiculo.marca.asc(), InventarioVehiculo.modelo.asc())
    if disponible is not None:
        statement = statement.where(InventarioVehiculo.disponible.is_(disponible))
    return list_records(db, tenant, statement, limit, offset)


def list_conversaciones(db: Session, tenant: TenantContext, limit: int, offset: int) -> dict[str, Any]:
    return list_records(db, tenant, select(Conversation).order_by(Conversation.creado_en.desc()), limit, offset)


def list_mensajes_dashboard(db: Session, tenant: TenantContext, limit: int, offset: int, whatsapp_id: str | None = None) -> dict[str, Any]:
    statement = select(Message).order_by(Message.creado_en.desc())
    if whatsapp_id:
        statement = statement.where(Message.whatsapp_id == whatsapp_id)
    return list_records(db, tenant, statement, limit, offset)


def list_solicitudes_derechos(db: Session, tenant: TenantContext, limit: int, offset: int) -> dict[str, Any]:
    return list_records(db, tenant, select(SolicitudDerecho).order_by(SolicitudDerecho.fecha_solicitud.desc()), limit, offset)


def list_ejecutivos(db: Session, tenant: TenantContext, limit: int, offset: int) -> dict[str, Any]:
    return list_records(db, tenant, select(Ejecutivo).order_by(Ejecutivo.nombre.asc()), limit, offset)


def list_log_limpiezas(db: Session, tenant: TenantContext, limit: int, offset: int) -> dict[str, Any]:
    return list_records(db, tenant, select(LogLimpieza).order_by(LogLimpieza.fecha_ejecucion.desc()), limit, offset)
