"""Meta omnichannel webhook routes, sync entity mappings, conflict reconciliation, and cursors."""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.integrations import (
    ChannelWebhookRouteCreateIn,
    ChannelWebhookRouteOut,
    ExternalMappingOut,
    ExternalMappingResolveIn,
    ExternalMappingUpsertIn,
    SyncCursorOut,
    SyncCursorUpsertIn,
)
from app.services.integrations_service import (
    create_webhook_route,
    deactivate_webhook_route,
    ingest_meta_webhook,
    list_external_mappings,
    list_sync_cursors,
    list_webhook_routes,
    resolve_external_mapping_conflict,
    upsert_external_mapping,
    upsert_sync_cursor,
    verify_meta_webhook_challenge,
)


router = APIRouter(prefix="/api/v1", tags=["Omnichannel & Sync Integrations"])


@router.get("/integrations/webhook-routes", response_model=list[ChannelWebhookRouteOut])
def webhook_routes_list(
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return list_webhook_routes(db, tenant)


@router.post("/integrations/webhook-routes", response_model=ChannelWebhookRouteOut, status_code=status.HTTP_201_CREATED)
def webhook_routes_create(
    payload: ChannelWebhookRouteCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return create_webhook_route(db, tenant, payload, actor_user_id=principal.user_id)


@router.post("/integrations/webhook-routes/{route_id}/deactivate", response_model=ChannelWebhookRouteOut)
def webhook_routes_deactivate(
    route_id: int,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return deactivate_webhook_route(db, tenant, route_id)


@router.get("/integrations/mappings", response_model=list[ExternalMappingOut])
def external_mappings_list(
    sync_state: str | None = Query(default=None, max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return list_external_mappings(db, tenant, sync_state=sync_state, limit=limit)


@router.post("/integrations/mappings", response_model=ExternalMappingOut)
def external_mappings_upsert(
    payload: ExternalMappingUpsertIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return upsert_external_mapping(db, tenant, payload, actor_user_id=principal.user_id)


@router.post("/integrations/mappings/{mapping_id}/resolve", response_model=ExternalMappingOut)
def external_mappings_resolve(
    mapping_id: int,
    payload: ExternalMappingResolveIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return resolve_external_mapping_conflict(db, tenant, mapping_id, payload, actor_user_id=principal.user_id)


@router.get("/integrations/cursors", response_model=list[SyncCursorOut])
def sync_cursors_list(
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return list_sync_cursors(db, tenant)


@router.put("/integrations/cursors", response_model=SyncCursorOut)
def sync_cursors_upsert(
    payload: SyncCursorUpsertIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return upsert_sync_cursor(db, tenant, payload)


@router.get("/public/webhooks/meta/{channel}")
def public_meta_webhook_challenge(
    channel: str,
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
    db: Session = Depends(get_db),
):
    challenge_value = verify_meta_webhook_challenge(
        db, channel=channel, mode=mode, verify_token=verify_token, challenge=challenge,
    )
    return PlainTextResponse(content=challenge_value, status_code=200)


@router.post("/public/webhooks/meta/{channel}")
async def public_meta_webhook_ingest(
    channel: str,
    request: Request,
    signature_header: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON webhook payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook body must be a JSON object")
    return ingest_meta_webhook(
        db,
        channel=channel,
        raw_body=raw_body,
        signature_header=signature_header,
        payload=payload,
    )
