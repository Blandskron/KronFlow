from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_resolver import TenantContext, resolve_tenant_from_jwt
from app.schemas.analytics import AnalyticsSummary
from app.services.analytics_service import analytics_summary

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
def summary(tenant: TenantContext = Depends(resolve_tenant_from_jwt), db: Session = Depends(get_db)):
    return analytics_summary(db, tenant)

