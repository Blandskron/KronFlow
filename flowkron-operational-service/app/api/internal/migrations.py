from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_internal_token
from app.schemas.tenant import MigrateAllResponse
from app.services.tenant_provisioning_service import migrate_all_tenants

router = APIRouter(prefix="/internal/migrations", tags=["Internal Migrations"], dependencies=[Depends(require_internal_token)])


@router.post("/run-all", response_model=MigrateAllResponse)
def run_all(db: Session = Depends(get_db)):
    return migrate_all_tenants(db)
