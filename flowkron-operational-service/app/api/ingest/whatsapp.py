from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.ingest.turns import router as turns_router
from app.core.rate_limit import enforce_ingest_rate_limit
from app.core.tenant_resolver import TenantContext, resolve_tenant_from_ingest_headers
from app.schemas.ingest import (
    ClientUpsertIn,
    ClientUpsertResponse,
    ConsentIn,
    ConsentOut,
    ConsentUpdateOut,
    CustomerOut,
    DashboardMessagesIn,
    DashboardMessagesResponse,
    ExecutiveAssignIn,
    ExecutiveLinkIn,
    HandoffIn,
    IngestResponse,
    LeadClassificationIn,
    LeadUpsertIn,
    LeadUpsertResponse,
    PrivacyRequestIn,
    PrivacyRequestResponse,
    WhatsAppMessageIn,
    WhatsAppStatusIn,
)
from app.schemas.whatsapp_turn import ProviderReceiptsIn, ProviderReceiptsOut
from app.services.ingest_service import (
    apply_lead_classification,
    assign_executive,
    create_handoff,
    get_consent,
    get_customer_by_phone,
    ingest_whatsapp_message,
    inventory_for_agent,
    link_executive,
    ordered_consent_ready,
    register_dashboard_messages,
    register_privacy_request,
    save_consent,
    update_whatsapp_status,
    upsert_client,
    upsert_lead,
)
from app.services.whatsapp_turn_service import record_provider_receipts, turn_jobs_ready, turn_receipts_ready

router = APIRouter(prefix="/api/v1/ingest/whatsapp", tags=["WhatsApp Ingest"])
router.include_router(turns_router)


@router.get("/runtime-ready", include_in_schema=False)
def runtime_ready(
    tenant: TenantContext = Depends(resolve_tenant_from_ingest_headers), db: Session = Depends(get_db),
):
    return {
        "status": "active", "durable_turns_ready": turn_jobs_ready(db, tenant),
        "provider_receipts_ready": turn_receipts_ready(db, tenant),
        "ordered_consent_ready": ordered_consent_ready(db, tenant),
    }


@router.post("/receipts", response_model=ProviderReceiptsOut)
def receipts(
    payload: ProviderReceiptsIn,
    x_baileys_token: str | None = Header(default=None),
    tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db),
):
    # The shared ingress resolver validates this token when the header is set.
    # A legacy ingestion key alone is insufficient to report provider evidence.
    if not x_baileys_token:
        raise HTTPException(status_code=401, detail="WhatsApp receipts require bridge credentials")
    return ProviderReceiptsOut(**record_provider_receipts(db, tenant, payload.receipts))


@router.post("/message", response_model=IngestResponse)
def message(payload: WhatsAppMessageIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    result = ingest_whatsapp_message(db, tenant, payload)
    return IngestResponse(**result)


@router.post("/lead-classification", response_model=IngestResponse)
def lead_classification(payload: LeadClassificationIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    result = apply_lead_classification(db, tenant, payload)
    return IngestResponse(**result)


@router.post("/handoff", response_model=IngestResponse)
def handoff(payload: HandoffIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    result = create_handoff(db, tenant, payload)
    return IngestResponse(**result)


@router.post("/status", response_model=IngestResponse)
def status(payload: WhatsAppStatusIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    result = update_whatsapp_status(db, tenant, payload)
    return IngestResponse(**result)


@router.get("/inventory")
def inventory(
    limit: int = Query(default=50, ge=1, le=100),
    tenant: TenantContext = Depends(enforce_ingest_rate_limit),
    db: Session = Depends(get_db),
):
    return {"items": inventory_for_agent(db, tenant, limit)}


@router.get("/customer", response_model=CustomerOut)
def customer(
    phone: str = Query(min_length=4, max_length=48),
    tenant: TenantContext = Depends(enforce_ingest_rate_limit),
    db: Session = Depends(get_db),
):
    return CustomerOut(**(get_customer_by_phone(db, tenant, phone) or {}))


@router.get("/consent", response_model=ConsentOut)
def consent(
    phone: str = Query(min_length=4, max_length=48),
    tenant: TenantContext = Depends(enforce_ingest_rate_limit),
    db: Session = Depends(get_db),
):
    return ConsentOut(**get_consent(db, tenant, phone))


@router.post("/consent", response_model=ConsentUpdateOut)
def consent_update(
    payload: ConsentIn,
    x_baileys_token: str | None = Header(default=None),
    tenant: TenantContext = Depends(resolve_tenant_from_ingest_headers),
    db: Session = Depends(get_db),
):
    if payload.sent_at is not None and not x_baileys_token:
        raise HTTPException(status_code=401, detail="Provider consent timestamps require bridge credentials")
    return ConsentUpdateOut(**save_consent(db, tenant, payload))


@router.post("/client", response_model=ClientUpsertResponse)
def client(payload: ClientUpsertIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return ClientUpsertResponse(**upsert_client(db, tenant, payload))


@router.post("/lead", response_model=LeadUpsertResponse)
def lead(payload: LeadUpsertIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return LeadUpsertResponse(**upsert_lead(db, tenant, payload))


@router.post("/privacy-requests", response_model=PrivacyRequestResponse)
def privacy_request(payload: PrivacyRequestIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return PrivacyRequestResponse(**register_privacy_request(db, tenant, payload))


@router.post("/dashboard-messages", response_model=DashboardMessagesResponse)
def dashboard_messages(payload: DashboardMessagesIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return DashboardMessagesResponse(**register_dashboard_messages(db, tenant, payload))


@router.post("/executives/assign")
def executive_assign(payload: ExecutiveAssignIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return assign_executive(db, tenant, payload)


@router.post("/executives/link")
def executive_link(payload: ExecutiveLinkIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return link_executive(db, tenant, payload)
