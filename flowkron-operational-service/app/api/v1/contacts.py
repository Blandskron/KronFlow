import re

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.tenant_resolver import TenantContext, resolve_tenant_from_jwt
from app.schemas.contact import ContactListResponse, ContactOut
from app.services.tenant_data import count_for_tenant, execute_for_tenant
from app.tenant_models.operations import Cliente

router = APIRouter(prefix="/api/v1/contacts", tags=["Contacts"])
contact_fields = (
    Cliente.id, Cliente.nombre.label("full_name"), Cliente.email, Cliente.telefono.label("phone"),
    Cliente.canal_origen.label("source"), Cliente.creado_en.label("created_at"),
)


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


@router.get("/{contact_id}", response_model=ContactOut)
def get_contact(
    contact_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt), db: Session = Depends(get_db),
):
    statement = select(*contact_fields).where(Cliente.id == contact_id)
    contact = execute_for_tenant(db, tenant.schema_name, statement).mappings().one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return ContactOut.model_validate(contact)
