from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.tenant_resolver import TenantContext, resolve_tenant_from_jwt
from app.schemas.contact import ContactListResponse
from app.services.tenant_data import count_for_tenant, execute_for_tenant
from app.tenant_models.operations import Cliente

router = APIRouter(prefix="/api/v1/contacts", tags=["Contacts"])


@router.get("", response_model=ContactListResponse)
def list_contacts(
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    limit = min(limit, settings.max_page_size)
    statement = select(
        Cliente.id, Cliente.nombre.label("full_name"), Cliente.email, Cliente.telefono.label("phone"),
        Cliente.canal_origen.label("source"), Cliente.creado_en.label("created_at"),
    )
    if q and (search := q.strip()):
        statement = statement.where(or_(
            Cliente.nombre.icontains(search, autoescape=True),
            Cliente.email.icontains(search, autoescape=True),
            Cliente.telefono.icontains(search, autoescape=True),
            Cliente.whatsapp_id.icontains(search, autoescape=True),
        ))
    total = count_for_tenant(db, tenant.schema_name, statement)
    page = statement.order_by(Cliente.creado_en.desc(), Cliente.id.desc()).limit(limit).offset(offset)
    items = execute_for_tenant(db, tenant.schema_name, page).mappings().all()
    return ContactListResponse(items=items, total=total, limit=limit, offset=offset)
