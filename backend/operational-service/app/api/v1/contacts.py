import re

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_audit_reader, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.contact import (
    ContactCreateIn,
    ContactCreateOut,
    ContactDetailOut,
    ContactListResponse,
    ContactMergeIn,
    ContactMergeOut,
    ContactNameUpdate,
    ContactOut,
    ContactPointsUpdate,
)
from app.schemas.contact_consent import ContactConsentOut
from app.schemas.lead import InitialLeadOut
from app.services.contact_merge_service import merge_contacts
from app.services.contact_points import normalize_email, normalize_phone
from app.services.contact_consent_service import read_contact_consent
from app.services.lead_service import ensure_contact_lead
from app.services.tenant_data import count_for_tenant, execute_for_tenant
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.operations import Cliente

router = APIRouter(prefix="/api/v1/contacts", tags=["Contacts"])
MANUAL_SOURCE = "crm_manual"
contact_fields = (
    Cliente.id, Cliente.nombre.label("full_name"), Cliente.email, Cliente.telefono.label("phone"),
    Cliente.canal_origen.label("source"), Cliente.creado_en.label("created_at"),
)


def _detail(contact) -> ContactDetailOut:
    return ContactDetailOut.model_validate({
        **contact,
        "normalized_email": normalize_email(contact["email"]),
        "normalized_phone": normalize_phone(contact["phone"]),
    })


@router.get("", response_model=ContactListResponse)
def list_contacts(
    q: str | None = Query(default=None, max_length=120),
    source: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    limit = min(limit, settings.max_page_size)
    statement = select(*contact_fields)
    if source:
        statement = statement.where(Cliente.canal_origen == source)
    if q and (search := q.strip()):
        matches = [
            Cliente.nombre.icontains(search, autoescape=True),
            Cliente.email.icontains(search, autoescape=True),
            Cliente.telefono.icontains(search, autoescape=True),
            Cliente.whatsapp_id.icontains(search, autoescape=True),
        ]
        if re.fullmatch(r"[0-9+().\s-]+", search):
            digits = re.sub(r"[^0-9]", "", search)
            if len(digits) >= 4:
                matches.extend(
                    func.regexp_replace(field, "[^0-9]", "", "g").contains(digits)
                    for field in (Cliente.telefono, Cliente.whatsapp_id)
                )
        statement = statement.where(or_(*matches))
    total = count_for_tenant(db, tenant.schema_name, statement)
    page = statement.order_by(Cliente.creado_en.desc(), Cliente.id.desc()).limit(limit).offset(offset)
    items = execute_for_tenant(db, tenant.schema_name, page).mappings().all()
    return ContactListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/sources", response_model=list[str])
def list_contact_sources(
    tenant: TenantContext = Depends(resolve_tenant_from_jwt), db: Session = Depends(get_db),
):
    source = Cliente.canal_origen
    statement = select(source).where(func.btrim(source) != "", func.length(source) <= 120).distinct().order_by(source).limit(100)
    return execute_for_tenant(db, tenant.schema_name, statement).scalars().all()


@router.post("", response_model=ContactCreateOut)
def create_contact(
    payload: ContactCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor), db: Session = Depends(get_db),
):
    # As with the legacy wa: reference, this identifies a non-RUT record in the existing table.
    reference = f"crm:{payload.request_id}"
    statement = insert(Cliente).values(
        rut=reference, nombre=payload.full_name, email=payload.email, telefono=payload.phone,
        canal_origen=MANUAL_SOURCE, consentimiento_datos=False,
    ).on_conflict_do_nothing(index_elements=[Cliente.rut]).returning(*contact_fields)
    contact = execute_for_tenant(db, tenant.schema_name, statement).mappings().one_or_none()
    if contact is None:
        existing = execute_for_tenant(db, tenant.schema_name, select(*contact_fields).where(
            Cliente.rut == reference, Cliente.canal_origen == MANUAL_SOURCE,
        )).mappings().one_or_none()
        if existing is None:
            raise HTTPException(status_code=409, detail="Contact creation reference is unavailable")
        return ContactCreateOut(contact=_detail(existing), created=False)

    create_system_event(db, "crm.contact.created", tenant.auth_tenant_id, tenant.schema_name, {"contact_id": contact["id"]})
    db.commit()
    return ContactCreateOut(contact=_detail(contact), created=True)


@router.get("/{contact_id}", response_model=ContactDetailOut)
def get_contact(
    contact_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt), db: Session = Depends(get_db),
):
    statement = select(*contact_fields).where(Cliente.id == contact_id)
    contact = execute_for_tenant(db, tenant.schema_name, statement).mappings().one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _detail(contact)


@router.get("/{contact_id}/whatsapp-consent", response_model=ContactConsentOut)
def contact_consent(
    contact_id: int = Path(ge=1, le=9223372036854775807),
    limit: int = Query(default=15, ge=1, le=50),
    before_id: int | None = Query(default=None, ge=1, le=2147483647),
    tenant: TenantContext = Depends(resolve_audit_reader), db: Session = Depends(get_db),
):
    return read_contact_consent(db, tenant, contact_id, limit, before_id)


@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact_name(
    payload: ContactNameUpdate,
    contact_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_crm_editor), db: Session = Depends(get_db),
):
    current = execute_for_tenant(db, tenant.schema_name, select(*contact_fields).where(
        Cliente.id == contact_id,
    ).with_for_update()).mappings().one_or_none()
    if current is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    if current["full_name"] != payload.expected_full_name:
        raise HTTPException(status_code=409, detail="Contact name changed since it was loaded")
    if current["full_name"] == payload.full_name:
        return ContactOut.model_validate(current)

    statement = update(Cliente).where(Cliente.id == contact_id).values(nombre=payload.full_name).returning(*contact_fields)
    contact = execute_for_tenant(db, tenant.schema_name, statement).mappings().one()
    create_system_event(db, "crm.contact.renamed", tenant.auth_tenant_id, tenant.schema_name, {"contact_id": contact_id})
    db.commit()
    return ContactOut.model_validate(contact)


@router.patch("/{contact_id}/points", response_model=ContactDetailOut)
def update_contact_points(
    payload: ContactPointsUpdate,
    contact_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_crm_editor), db: Session = Depends(get_db),
):
    current = execute_for_tenant(db, tenant.schema_name, select(*contact_fields).where(
        Cliente.id == contact_id,
    ).with_for_update()).mappings().one_or_none()
    if current is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    if current["source"] != MANUAL_SOURCE:
        raise HTTPException(status_code=409, detail="Contact points are managed by the original integration")
    if (current["email"], current["phone"]) != (payload.expected_email, payload.expected_phone):
        raise HTTPException(status_code=409, detail="Contact points changed since they were loaded")
    changes = [field for field in ("email", "phone") if current[field] != getattr(payload, field)]
    if not changes:
        return _detail(current)

    statement = update(Cliente).where(Cliente.id == contact_id).values(
        email=payload.email, telefono=payload.phone,
    ).returning(*contact_fields)
    contact = execute_for_tenant(db, tenant.schema_name, statement).mappings().one()
    create_system_event(db, "crm.contact.points.changed", tenant.auth_tenant_id, tenant.schema_name, {
        "contact_id": contact_id, "fields": changes,
    })
    db.commit()
    return _detail(contact)


@router.post("/{contact_id}/lead", response_model=InitialLeadOut)
def start_contact_lead(
    contact_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_crm_editor), db: Session = Depends(get_db),
):
    return ensure_contact_lead(db, tenant, contact_id)


@router.post("/{contact_id}/merge", response_model=ContactMergeOut)
def merge_contact_endpoint(
    payload: ContactMergeIn,
    contact_id: int = Path(ge=1, le=9223372036854775807),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return merge_contacts(db, tenant, contact_id, payload, actor_user_id=principal.user_id)
