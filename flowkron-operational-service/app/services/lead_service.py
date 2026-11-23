from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.tenant_resolver import TenantContext
from app.schemas.lead import LeadUpdate
from app.services.tenant_data import bind_tenant_session, count_for_tenant, execute_for_tenant, lead_to_dict, scalar_for_tenant
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.operations import Cliente, Ejecutivo, Lead

TERMINAL_STAGES = ("ganado", "perdido")


def _filtered_leads_statement(
    temperature: str | None = None,
    lifecycle_status: str | None = None,
    direction: str | None = None,
    *, search: str | None = None, contact_id: int | None = None, status_group: str | None = None,
):
    if direction and direction != "inbound":
        return select(Lead).where(False)
    statement = select(Lead).options(selectinload(Lead.cliente))
    if temperature:
        classification = {"cold": "frio", "warm": "tibio", "hot": "caliente"}.get(temperature, temperature)
        statement = statement.where(Lead.clasificacion == classification)
    if lifecycle_status:
        statement = statement.where(Lead.estado == lifecycle_status)
    if status_group == "open":
        statement = statement.where(Lead.estado.not_in(TERMINAL_STAGES))
    elif status_group == "closed":
        statement = statement.where(Lead.estado.in_(TERMINAL_STAGES))
    if contact_id is not None:
        statement = statement.where(Lead.cliente_id == contact_id)
    if search and (term := search.strip()):
        statement = statement.join(Lead.cliente).where(or_(
            Cliente.nombre.icontains(term, autoescape=True), Cliente.email.icontains(term, autoescape=True),
            Cliente.telefono.icontains(term, autoescape=True),
        ))
    return statement


def list_leads(
    db: Session,
    tenant: TenantContext,
    limit: int,
    offset: int,
    temperature: str | None = None,
    lifecycle_status: str | None = None,
    direction: str | None = None,
    *, search: str | None = None, contact_id: int | None = None, status_group: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    base_statement = _filtered_leads_statement(
        temperature, lifecycle_status, direction, search=search, contact_id=contact_id, status_group=status_group,
    )
    total = count_for_tenant(db, tenant.schema_name, base_statement)
    statement = base_statement.order_by(Lead.actualizado_en.desc(), Lead.id.desc()).limit(limit).offset(offset)
    items = execute_for_tenant(db, tenant.schema_name, statement).scalars().all()
    return [lead_to_dict(item) for item in items], total


def get_lead(db: Session, tenant: TenantContext, lead_id: int) -> dict[str, Any] | None:
    lead = scalar_for_tenant(db, tenant.schema_name, select(Lead).options(selectinload(Lead.cliente)).where(Lead.id == lead_id))
    return lead_to_dict(lead) if lead else None


def update_lead(db: Session, tenant: TenantContext, lead_id: int, payload: LeadUpdate) -> dict[str, Any] | None:
    bind_tenant_session(db, tenant.schema_name)
    statement = select(Lead).options(selectinload(Lead.cliente)).where(Lead.id == lead_id)
    if payload.expected_updated_at is not None or payload.lifecycle_status is not None:
        statement = statement.with_for_update()
    lead = scalar_for_tenant(db, tenant.schema_name, statement)
    if not lead:
        return None
    if payload.expected_updated_at is not None and lead.actualizado_en != payload.expected_updated_at:
        raise HTTPException(status_code=409, detail="Lead changed since it was loaded")

    data = payload.model_dump(exclude_unset=True)
    if "full_name" in data and lead.cliente:
        lead.cliente.nombre = data["full_name"] or lead.cliente.nombre
    if "email" in data and lead.cliente:
        lead.cliente.email = data["email"]
    if "temperature" in data:
        lead.clasificacion = {"cold": "frio", "warm": "tibio", "hot": "caliente"}.get(data["temperature"], data["temperature"])
    if "lifecycle_status" in data:
        if lead.estado != data["lifecycle_status"]:
            create_system_event(db, "crm.lead.stage.changed", tenant.auth_tenant_id, tenant.schema_name, {
                "lead_id": lead.id, "previous_stage": lead.estado, "stage": data["lifecycle_status"],
            })
        lead.estado = data["lifecycle_status"]
    if "assigned_to_user_id" in data:
        assigned = data["assigned_to_user_id"]
        if assigned is not None and scalar_for_tenant(
            db, tenant.schema_name, select(Ejecutivo.id).where(Ejecutivo.id == assigned),
        ) is None:
            raise HTTPException(status_code=422, detail="Executive does not exist in the workspace")
        lead.ejecutivo_id = data["assigned_to_user_id"]
    if "score" in data:
        lead.score_lead = data["score"]

    db.commit()
    db.refresh(lead)
    return lead_to_dict(lead)
