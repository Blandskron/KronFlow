from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.tenant_resolver import TenantContext
from app.public_models.system_event import SystemEvent
from app.schemas.lead import LeadUpdate
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.tenant_data import TEMPERATURE_TO_API, bind_tenant_session, count_for_tenant, execute_for_tenant, lead_to_dict, scalar_for_tenant
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.operations import Cliente, Ejecutivo, Lead

TERMINAL_STAGES = ("ganado", "perdido")
ACTIVITY_KINDS = {
    "crm.lead.created": "created",
    "crm.lead.stage.changed": "stage",
    "crm.lead.temperature.changed": "temperature",
}


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


def get_or_create_initial_lead(db: Session, contact_id: int) -> tuple[Lead, bool]:
    # Callers use a tenant-bound session. The existing contact serializes competing writers, including ingest.
    contact = db.scalar(select(Cliente).where(Cliente.id == contact_id).with_for_update())
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    lead = db.scalar(select(Lead).where(Lead.cliente_id == contact_id).order_by(Lead.id).limit(1))
    if lead is not None:
        return lead, False
    lead = Lead(cliente=contact)
    db.add(lead)
    db.flush()
    return lead, True


def ensure_contact_lead(db: Session, tenant: TenantContext, contact_id: int) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    lead, created = get_or_create_initial_lead(db, contact_id)
    if created:
        create_system_event(db, "crm.lead.created", tenant.auth_tenant_id, tenant.schema_name, {"lead_id": lead.id})
        publish_domain_event_in_tx(
            db,
            tenant,
            event_type="lead.created",
            aggregate_type="lead",
            aggregate_id=lead.id,
            payload={"lead_id": lead.id, "contact_id": contact_id},
        )
    result = {"lead": lead_to_dict(lead), "created": created}
    db.commit()
    return result


def list_lead_activity(db: Session, tenant: TenantContext, lead_id: int, limit: int) -> list[dict[str, Any]]:
    if scalar_for_tenant(db, tenant.schema_name, select(Lead.id).where(Lead.id == lead_id)) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    statement = select(SystemEvent).where(
        SystemEvent.auth_tenant_id == tenant.auth_tenant_id,
        SystemEvent.schema_name == tenant.schema_name,
        SystemEvent.event_type.in_(ACTIVITY_KINDS),
        SystemEvent.payload["lead_id"].astext == str(lead_id),
    ).order_by(SystemEvent.created_at.desc(), SystemEvent.id.desc()).limit(limit)
    activity = []
    for event in db.scalars(statement):
        kind = ACTIVITY_KINDS[event.event_type]
        activity.append({
            "id": event.id, "kind": kind, "created_at": event.created_at,
            "previous": event.payload.get(f"previous_{kind}"), "value": event.payload.get(kind),
        })
    return activity


def update_lead(db: Session, tenant: TenantContext, lead_id: int, payload: LeadUpdate) -> dict[str, Any] | None:
    bind_tenant_session(db, tenant.schema_name)
    statement = select(Lead).options(selectinload(Lead.cliente)).where(Lead.id == lead_id)
    if payload.expected_updated_at is not None or payload.lifecycle_status is not None or payload.temperature is not None:
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
        classification = {"cold": "frio", "warm": "tibio", "hot": "caliente"}.get(data["temperature"], data["temperature"])
        if lead.clasificacion != classification:
            prev_temp = TEMPERATURE_TO_API[lead.clasificacion]
            next_temp = TEMPERATURE_TO_API[classification]
            create_system_event(db, "crm.lead.temperature.changed", tenant.auth_tenant_id, tenant.schema_name, {
                "lead_id": lead.id, "previous_temperature": prev_temp,
                "temperature": next_temp,
            })
            publish_domain_event_in_tx(
                db,
                tenant,
                event_type="lead.temperature.changed",
                aggregate_type="lead",
                aggregate_id=lead.id,
                payload={
                    "lead_id": lead.id,
                    "contact_id": lead.cliente_id,
                    "previous_temperature": prev_temp,
                    "temperature": next_temp,
                },
            )
        lead.clasificacion = classification
    if "lifecycle_status" in data:
        if lead.estado != data["lifecycle_status"]:
            create_system_event(db, "crm.lead.stage.changed", tenant.auth_tenant_id, tenant.schema_name, {
                "lead_id": lead.id, "previous_stage": lead.estado, "stage": data["lifecycle_status"],
            })
            publish_domain_event_in_tx(
                db,
                tenant,
                event_type="lead.stage.changed",
                aggregate_type="lead",
                aggregate_id=lead.id,
                payload={
                    "lead_id": lead.id,
                    "contact_id": lead.cliente_id,
                    "previous_stage": lead.estado,
                    "stage": data["lifecycle_status"],
                },
            )
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
