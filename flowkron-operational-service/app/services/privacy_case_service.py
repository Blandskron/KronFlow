from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.privacy_case import CaseState, PrivacyCaseTransition
from app.services.tenant_data import count_for_tenant, execute_for_tenant
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.operations import SolicitudDerecho


CASE_FIELDS = (
    SolicitudDerecho.id, SolicitudDerecho.tipo_derecho.label("kind"), SolicitudDerecho.estado.label("state"),
    SolicitudDerecho.fecha_solicitud.label("requested_at"), SolicitudDerecho.fecha_limite.label("due_at"),
    SolicitudDerecho.fecha_resolucion.label("completed_at"),
)
NEXT_STATE = {"pendiente": "en_proceso", "en_proceso": "completada"}


def list_privacy_cases(db: Session, tenant: TenantContext, state: CaseState | None, limit: int, offset: int) -> dict:
    statement = select(*CASE_FIELDS)
    if state is not None:
        statement = statement.where(SolicitudDerecho.estado == state)
    total = count_for_tenant(db, tenant.schema_name, statement)
    page = statement.order_by(SolicitudDerecho.fecha_limite, SolicitudDerecho.id).limit(limit).offset(offset)
    items = execute_for_tenant(db, tenant.schema_name, page).mappings().all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def transition_privacy_case(
    db: Session, tenant: TenantContext, case_id: int, transition: PrivacyCaseTransition, actor_id: str,
):
    if NEXT_STATE[transition.expected_state] != transition.state:
        raise HTTPException(status_code=422, detail="Invalid privacy case transition")
    closing = transition.state == "completada"
    if closing and not transition.confirmed:
        raise HTTPException(status_code=422, detail="Confirm the request was handled before closing")

    target = SolicitudDerecho.id == case_id
    current = execute_for_tenant(db, tenant.schema_name, select(*CASE_FIELDS).where(target).with_for_update()).mappings().one_or_none()
    if current is None:
        raise HTTPException(status_code=404, detail="Privacy case not found")
    if current["state"] == transition.state:
        return current
    if current["state"] != transition.expected_state:
        raise HTTPException(status_code=409, detail="Privacy case state changed since it was loaded")

    statement = update(SolicitudDerecho).where(target).values(
        estado=transition.state, fecha_resolucion=func.now() if closing else None,
    ).returning(*CASE_FIELDS)
    result = execute_for_tenant(db, tenant.schema_name, statement).mappings().one()
    create_system_event(db, "privacy.case.state.changed", tenant.auth_tenant_id, tenant.schema_name, {
        "case_id": case_id, "previous_state": transition.expected_state, "state": transition.state, "actor_id": actor_id,
    })
    db.commit()
    return result
