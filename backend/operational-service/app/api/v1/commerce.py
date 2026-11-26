"""Commercial order API endpoints and signed Shopify / Mercado Pago payment webhooks."""

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.commerce import CommerceOrderCreateIn, CommerceRefundIn
from app.services.commerce_service import (
    create_checkout_link,
    create_commerce_order,
    ingest_mercadopago_webhook,
    ingest_shopify_webhook,
    list_commerce_orders,
    list_order_events,
    record_commerce_refund,
)


router = APIRouter(prefix="/api/v1", tags=["Commerce"])


@router.get("/commerce/orders")
def list_commerce_orders_endpoint(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    _principal: CurrentPrincipal = Depends(require_permission("users.read")),
    db: Session = Depends(get_db),
):
    return list_commerce_orders(db, tenant, status_filter=status, limit=limit)


@router.post("/commerce/orders")
def create_commerce_order_endpoint(
    payload: CommerceOrderCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return create_commerce_order(db, tenant, payload, actor_user_id=principal.user_id)


@router.post("/commerce/orders/{order_id}/checkout-link")
def create_checkout_link_endpoint(
    order_id: int,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return create_checkout_link(db, tenant, order_id, actor_user_id=principal.user_id)


@router.post("/commerce/orders/{order_id}/refund")
def record_commerce_refund_endpoint(
    order_id: int,
    payload: CommerceRefundIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return record_commerce_refund(db, tenant, order_id, payload, actor_user_id=principal.user_id)


@router.get("/commerce/orders/{order_id}/events")
def list_order_events_endpoint(
    order_id: int,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    _principal: CurrentPrincipal = Depends(require_permission("users.read")),
    db: Session = Depends(get_db),
):
    return list_order_events(db, tenant, order_id)


@router.post("/public/webhooks/commerce/shopify")
async def shopify_commerce_webhook_endpoint(
    request: Request,
    x_shopify_shop_domain: str = Header(..., alias="X-Shopify-Shop-Domain"),
    x_shopify_webhook_id: str = Header(..., alias="X-Shopify-Webhook-Id"),
    x_shopify_topic: str = Header(default="orders/paid", alias="X-Shopify-Topic"),
    x_shopify_hmac_sha256: str | None = Header(default=None, alias="X-Shopify-Hmac-Sha256"),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    payload = await request.json()
    return ingest_shopify_webhook(
        db,
        shop_domain=x_shopify_shop_domain,
        webhook_id=x_shopify_webhook_id,
        topic=x_shopify_topic,
        hmac_header=x_shopify_hmac_sha256,
        raw_body=raw_body,
        payload=payload if isinstance(payload, dict) else {},
    )


@router.post("/public/webhooks/commerce/mercadopago")
async def mercadopago_commerce_webhook_endpoint(
    request: Request,
    account_id: str = Query(..., min_length=1),
    x_signature: str | None = Header(default=None, alias="x-signature"),
    x_request_id: str | None = Header(default=None, alias="x-request-id"),
    db: Session = Depends(get_db),
):
    payload = await request.json()
    return ingest_mercadopago_webhook(
        db,
        account_id=account_id,
        x_signature=x_signature,
        x_request_id=x_request_id,
        payload=payload if isinstance(payload, dict) else {},
    )
