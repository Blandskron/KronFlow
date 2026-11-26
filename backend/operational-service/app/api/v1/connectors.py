"""Outbound connector API routes (WhatsApp Cloud API, Google Calendar, HubSpot)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor
from app.schemas.connectors import (
    ConnectorSyncResultOut,
    GoogleCalendarPushIn,
    GoogleCalendarSyncIn,
    HubSpotSyncIn,
    WhatsAppCloudSendIn,
    WhatsAppCloudSendOut,
)
from app.services.connectors_service import (
    push_appointment_to_google_calendar,
    send_whatsapp_cloud_message,
    sync_google_calendar_events,
    sync_hubspot_crm,
)


router = APIRouter(prefix="/api/v1/connectors", tags=["Connectors"])


@router.post("/whatsapp-cloud/send", response_model=WhatsAppCloudSendOut)
def whatsapp_cloud_send_endpoint(
    payload: WhatsAppCloudSendIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return send_whatsapp_cloud_message(db, tenant, payload, actor_user_id=principal.user_id)


@router.post("/google-calendar/appointments/{appointment_id}/push")
def google_calendar_push_endpoint(
    appointment_id: int,
    payload: GoogleCalendarPushIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return push_appointment_to_google_calendar(db, tenant, appointment_id, payload, actor_user_id=principal.user_id)


@router.post("/google-calendar/sync", response_model=ConnectorSyncResultOut)
def google_calendar_sync_endpoint(
    payload: GoogleCalendarSyncIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return sync_google_calendar_events(db, tenant, payload, actor_user_id=principal.user_id)


@router.post("/hubspot/sync", response_model=ConnectorSyncResultOut)
def hubspot_sync_endpoint(
    payload: HubSpotSyncIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return sync_hubspot_crm(db, tenant, payload, actor_user_id=principal.user_id)
