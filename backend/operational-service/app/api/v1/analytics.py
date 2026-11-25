from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_resolver import TenantContext, resolve_tenant_from_jwt
from app.schemas.analytics import AnalyticsActivity, AnalyticsKpisOut, AnalyticsSummary
from app.services.analytics_service import analytics_activity, analytics_kpis, analytics_summary

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
def summary(tenant: TenantContext = Depends(resolve_tenant_from_jwt), db: Session = Depends(get_db)):
    return analytics_summary(db, tenant)


@router.get("/activity", response_model=AnalyticsActivity)
def activity(
    start_date: date,
    end_date: date,
    time_zone: str = Query(default="UTC", max_length=64, pattern=r"^(UTC|[A-Za-z_]+(?:/[A-Za-z0-9_+\-]+)+)$"),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return analytics_activity(db, tenant, start_date, end_date, time_zone)


@router.get("/kpis", response_model=AnalyticsKpisOut)
def kpis(tenant: TenantContext = Depends(resolve_tenant_from_jwt), db: Session = Depends(get_db)):
    return analytics_kpis(db, tenant)

