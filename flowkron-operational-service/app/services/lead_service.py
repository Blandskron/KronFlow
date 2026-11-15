from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.tenant_resolver import TenantContext
from app.schemas.lead import LeadUpdate
from app.services.tenant_data import bind_tenant_session, count_for_tenant, execute_for_tenant, lead_to_dict, scalar_for_tenant
from app.tenant_models.operations import Lead


def _filtered_leads_statement(
    temperature: str | None = None,
    lifecycle_status: str | None = None,
    direction: str | None = None,
):
    if direction and direction != "inbound":
        return select(Lead).where(False)
    statement = select(Lead).options(selectinload(Lead.cliente))
    if temperature:
        classification = {"cold": "frio", "warm": "tibio", "hot": "caliente"}.get(temperature, temperature)
        statement = statement.where(Lead.clasificacion == classification)
    if lifecycle_status:
        statement = statement.where(Lead.estado == lifecycle_status)
    return statement


def list_leads(
    db: Session,
    tenant: TenantContext,
    limit: int,
    offset: int,
    temperature: str | None = None,
    lifecycle_status: str | None = None,
    direction: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    base_statement = _filtered_leads_statement(temperature, lifecycle_status, direction)
    total = count_for_tenant(db, tenant.schema_name, base_statement)
    statement = base_statement.order_by(Lead.actualizado_en.desc()).limit(limit).offset(offset)
    items = execute_for_tenant(db, tenant.schema_name, statement).scalars().all()
    return [lead_to_dict(item) for item in items], total


def get_lead(db: Session, tenant: TenantContext, lead_id: int) -> dict[str, Any] | None:
    lead = scalar_for_tenant(db, tenant.schema_name, select(Lead).options(selectinload(Lead.cliente)).where(Lead.id == lead_id))
    return lead_to_dict(lead) if lead else None


def update_lead(db: Session, tenant: TenantContext, lead_id: int, payload: LeadUpdate) -> dict[str, Any] | None:
    bind_tenant_session(db, tenant.schema_name)
    lead = scalar_for_tenant(db, tenant.schema_name, select(Lead).options(selectinload(Lead.cliente)).where(Lead.id == lead_id))
    if not lead:
        return None

    data = payload.model_dump(exclude_unset=True)
    if "full_name" in data and lead.cliente:
        lead.cliente.nombre = data["full_name"] or lead.cliente.nombre
    if "email" in data and lead.cliente:
        lead.cliente.email = data["email"]
    if "temperature" in data:
        lead.clasificacion = {"cold": "frio", "warm": "tibio", "hot": "caliente"}.get(data["temperature"], data["temperature"])
    if "lifecycle_status" in data:
        lead.estado = data["lifecycle_status"]
    if "assigned_to_user_id" in data:
        lead.ejecutivo_id = data["assigned_to_user_id"]
    if "score" in data:
        lead.score_lead = data["score"]

    db.commit()
    db.refresh(lead)
    return lead_to_dict(lead)
