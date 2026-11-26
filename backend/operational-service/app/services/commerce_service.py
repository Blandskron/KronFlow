"""Commercial order lifecycle, checkout links, refunds, and Shopify/Mercado Pago reconciliation."""

import base64
from datetime import datetime, timezone
import hashlib
import hmac
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.tenant_resolver import TenantContext, ensure_runtime_is_usable
from app.public_models.channel_route import PublicChannelWebhookRoute
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.commerce import CommerceOrderCreateIn, CommerceRefundIn
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.phase6_extensions import CommerceOrder, CommercePaymentEvent


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Commerce timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _require_commerce_ready(db: Session, tenant: TenantContext) -> None:
    inspector = inspect(db.connection())
    existing = set(inspector.get_table_names(schema=tenant.schema_name))
    if not {CommerceOrder.__tablename__, CommercePaymentEvent.__tablename__}.issubset(existing):
        raise HTTPException(status_code=503, detail="Commerce schema is unavailable")


def _order_to_dict(order: CommerceOrder) -> dict[str, Any]:
    net_minor = max(0, int(order.confirmed_amount_minor) - int(order.refunded_amount_minor))
    return {
        "id": order.id,
        "provider": order.provider,
        "external_order_id": order.external_order_id,
        "order_number": order.order_number,
        "client_id": order.client_id,
        "opportunity_id": order.opportunity_id,
        "conversation_id": order.conversation_id,
        "currency": order.currency,
        "expected_amount_minor": order.expected_amount_minor,
        "confirmed_amount_minor": order.confirmed_amount_minor,
        "refunded_amount_minor": order.refunded_amount_minor,
        "net_confirmed_minor": net_minor,
        "status": order.status,
        "checkout_url": order.checkout_url,
        "discrepancy_reason": order.discrepancy_reason,
        "metadata": dict(order.metadata_json or {}),
        "created_by": order.created_by,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def _event_to_dict(ev: CommercePaymentEvent) -> dict[str, Any]:
    return {
        "id": ev.id,
        "order_id": ev.order_id,
        "provider": ev.provider,
        "external_event_id": ev.external_event_id,
        "external_payment_id": ev.external_payment_id,
        "event_type": ev.event_type,
        "currency": ev.currency,
        "amount_minor": ev.amount_minor,
        "occurred_at": ev.occurred_at,
        "recorded_at": ev.recorded_at,
    }


def list_commerce_orders(
    db: Session,
    tenant: TenantContext,
    *,
    status_filter: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    _require_commerce_ready(db, tenant)
    stmt = select(CommerceOrder).order_by(CommerceOrder.id.desc()).limit(max(1, min(limit, 200)))
    if status_filter:
        stmt = stmt.where(CommerceOrder.status == status_filter.strip())
    return [_order_to_dict(row) for row in db.scalars(stmt).all()]


def list_order_events(db: Session, tenant: TenantContext, order_id: int) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    _require_commerce_ready(db, tenant)
    if db.get(CommerceOrder, order_id) is None:
        raise HTTPException(status_code=404, detail="Commerce order not found")
    rows = list(
        db.scalars(
            select(CommercePaymentEvent)
            .where(CommercePaymentEvent.order_id == order_id)
            .order_by(CommercePaymentEvent.id.asc())
        ).all()
    )
    return [_event_to_dict(row) for row in rows]


def create_commerce_order(
    db: Session,
    tenant: TenantContext,
    payload: CommerceOrderCreateIn,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_commerce_ready(db, tenant)

    ext_id = payload.external_order_id.strip()[:160] if payload.external_order_id else None
    if ext_id:
        existing = db.scalar(
            select(CommerceOrder).where(
                CommerceOrder.provider == payload.provider,
                CommerceOrder.external_order_id == ext_id,
            )
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="Commerce order external_order_id already registered")

    order = CommerceOrder(
        provider=payload.provider,
        external_order_id=ext_id,
        order_number=f"ord_{uuid4().hex[:14]}",
        client_id=payload.client_id,
        opportunity_id=payload.opportunity_id,
        conversation_id=payload.conversation_id,
        currency=payload.currency.upper(),
        expected_amount_minor=payload.expected_amount_minor,
        confirmed_amount_minor=0,
        refunded_amount_minor=0,
        status="draft",
        metadata_json=dict(payload.metadata or {}),
        created_by=actor_user_id[:64] if actor_user_id else None,
        created_at=current,
        updated_at=current,
    )
    db.add(order)
    db.flush()
    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="commerce.order.created",
        aggregate_type="commerce_order",
        aggregate_id=order.id,
        payload={
            "order_id": order.id,
            "order_number": order.order_number,
            "provider": order.provider,
            "currency": order.currency,
            "expected_amount_minor": order.expected_amount_minor,
        },
        occurred_at=current,
    )
    db.commit()
    db.refresh(order)
    return _order_to_dict(order)


def create_checkout_link(
    db: Session,
    tenant: TenantContext,
    order_id: int,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_commerce_ready(db, tenant)

    order = db.scalar(select(CommerceOrder).where(CommerceOrder.id == order_id).with_for_update())
    if order is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Commerce order not found")
    if order.status not in ("draft", "checkout_created"):
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Cannot issue checkout link from order status '{order.status}'")

    if not order.checkout_url:
        base = (get_settings().public_api_base_url or f"https://checkout.{order.provider}.example").rstrip("/")
        order.checkout_url = f"{base}/pay/{order.order_number}"
    order.status = "checkout_created"
    order.updated_at = current

    create_system_event(
        db,
        "commerce.checkout.created",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"order_id": order.id, "order_number": order.order_number, "actor_user_id": actor_user_id},
    )
    db.commit()
    db.refresh(order)
    return _order_to_dict(order)


def _apply_refund_in_tx(
    db: Session,
    tenant: TenantContext,
    order: CommerceOrder,
    *,
    provider: str,
    external_event_id: str,
    external_payment_id: str | None,
    currency: str,
    amount_minor: int,
    payload_json: dict[str, Any],
    now: datetime,
) -> tuple[CommerceOrder, bool]:
    existing_ev = db.scalar(
        select(CommercePaymentEvent).where(
            CommercePaymentEvent.provider == provider,
            CommercePaymentEvent.external_event_id == external_event_id,
        )
    )
    if existing_ev is not None:
        return order, True

    if currency.upper() != order.currency:
        order.status = "discrepancy"
        order.discrepancy_reason = f"Refund currency mismatch: expected {order.currency}, got {currency.upper()}"
        order.updated_at = now
        db.add(
            CommercePaymentEvent(
                order_id=order.id,
                provider=provider,
                external_event_id=external_event_id,
                external_payment_id=external_payment_id,
                event_type="discrepancy_flagged",
                currency=currency.upper()[:3],
                amount_minor=0,
                payload_json=payload_json,
                occurred_at=now,
                recorded_at=now,
            )
        )
        return order, False

    remaining = int(order.confirmed_amount_minor) - int(order.refunded_amount_minor)
    if remaining <= 0 or amount_minor > remaining:
        raise HTTPException(
            status_code=422,
            detail=f"Refund amount {amount_minor} exceeds remaining confirmed balance {remaining}",
        )

    order.refunded_amount_minor = int(order.refunded_amount_minor) + amount_minor
    order.status = "refunded" if order.refunded_amount_minor >= int(order.confirmed_amount_minor) else "partially_refunded"
    order.updated_at = now
    db.add(
        CommercePaymentEvent(
            order_id=order.id,
            provider=provider,
            external_event_id=external_event_id,
            external_payment_id=external_payment_id,
            event_type="refund_confirmed",
            currency=order.currency,
            amount_minor=-amount_minor,
            payload_json=payload_json,
            occurred_at=now,
            recorded_at=now,
        )
    )
    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="commerce.order.refunded",
        aggregate_type="commerce_order",
        aggregate_id=order.id,
        payload={
            "order_id": order.id,
            "order_number": order.order_number,
            "currency": order.currency,
            "refunded_amount_minor": amount_minor,
            "net_confirmed_minor": int(order.confirmed_amount_minor) - int(order.refunded_amount_minor),
        },
        occurred_at=now,
    )
    return order, False


def record_commerce_refund(
    db: Session,
    tenant: TenantContext,
    order_id: int,
    payload: CommerceRefundIn,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_commerce_ready(db, tenant)

    order = db.scalar(select(CommerceOrder).where(CommerceOrder.id == order_id).with_for_update())
    if order is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Commerce order not found")

    ext_ev = (payload.external_event_id or f"manual-refund:{uuid4().hex[:16]}").strip()[:160]
    order, duplicate = _apply_refund_in_tx(
        db,
        tenant,
        order,
        provider=order.provider,
        external_event_id=ext_ev,
        external_payment_id=None,
        currency=order.currency,
        amount_minor=payload.amount_minor,
        payload_json={"reason": payload.reason, "actor_user_id": actor_user_id},
        now=current,
    )
    db.commit()
    db.refresh(order)
    res = _order_to_dict(order)
    res["duplicate"] = duplicate
    return res


def _resolve_route_and_tenant(db: Session, *, channel: str, external_account_id: str) -> tuple[PublicChannelWebhookRoute, TenantContext]:
    route = db.scalar(
        select(PublicChannelWebhookRoute).where(
            PublicChannelWebhookRoute.channel == channel,
            PublicChannelWebhookRoute.external_account_id == external_account_id,
            PublicChannelWebhookRoute.is_active.is_(True),
        )
    )
    if route is None:
        raise HTTPException(status_code=404, detail=f"{channel} webhook route not found or inactive")
    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == route.auth_tenant_id))
    if runtime is None:
        raise HTTPException(status_code=404, detail="Tenant runtime not provisioned")
    ensure_runtime_is_usable(runtime)
    tenant = TenantContext(
        auth_tenant_id=runtime.auth_tenant_id,
        tenant_slug=runtime.tenant_slug,
        schema_name=runtime.schema_name,
        tenant_code=runtime.tenant_code,
        plan=runtime.plan,
        status=runtime.status,
    )
    return route, tenant


def _reconcile_payment_in_tx(
    db: Session,
    tenant: TenantContext,
    order: CommerceOrder,
    *,
    provider: str,
    external_event_id: str,
    external_payment_id: str | None,
    currency: str,
    amount_minor: int,
    payload_json: dict[str, Any],
    now: datetime,
) -> tuple[CommerceOrder, bool]:
    existing_ev = db.scalar(
        select(CommercePaymentEvent).where(
            CommercePaymentEvent.provider == provider,
            CommercePaymentEvent.external_event_id == external_event_id,
        )
    )
    if existing_ev is not None:
        return order, True

    norm_curr = currency.upper()[:3]
    if norm_curr != order.currency or amount_minor != int(order.expected_amount_minor):
        order.status = "discrepancy"
        order.discrepancy_reason = (
            f"Expected {order.expected_amount_minor} {order.currency}, got {amount_minor} {norm_curr}"
        )
        order.updated_at = now
        db.add(
            CommercePaymentEvent(
                order_id=order.id,
                provider=provider,
                external_event_id=external_event_id,
                external_payment_id=external_payment_id,
                event_type="discrepancy_flagged",
                currency=norm_curr,
                amount_minor=0,
                payload_json=payload_json,
                occurred_at=now,
                recorded_at=now,
            )
        )
        create_system_event(
            db,
            "commerce.payment.discrepancy",
            tenant.auth_tenant_id,
            tenant.schema_name,
            {"order_id": order.id, "order_number": order.order_number, "reason": order.discrepancy_reason},
        )
        return order, False

    order.confirmed_amount_minor = amount_minor
    order.status = "paid"
    order.discrepancy_reason = None
    order.updated_at = now
    db.add(
        CommercePaymentEvent(
            order_id=order.id,
            provider=provider,
            external_event_id=external_event_id,
            external_payment_id=external_payment_id,
            event_type="payment_confirmed",
            currency=order.currency,
            amount_minor=amount_minor,
            payload_json=payload_json,
            occurred_at=now,
            recorded_at=now,
        )
    )
    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="commerce.order.paid",
        aggregate_type="commerce_order",
        aggregate_id=order.id,
        payload={
            "order_id": order.id,
            "order_number": order.order_number,
            "provider": provider,
            "currency": order.currency,
            "confirmed_amount_minor": amount_minor,
        },
        occurred_at=now,
    )
    return order, False


def _locate_order_for_update(
    db: Session,
    *,
    provider: str,
    external_order_id: str | None,
    order_number: str | None,
) -> CommerceOrder | None:
    if external_order_id:
        found = db.scalar(
            select(CommerceOrder)
            .where(CommerceOrder.provider == provider, CommerceOrder.external_order_id == external_order_id)
            .with_for_update()
        )
        if found is not None:
            return found
    if order_number:
        return db.scalar(
            select(CommerceOrder).where(CommerceOrder.order_number == order_number).with_for_update()
        )
    return None


def ingest_shopify_webhook(
    db: Session,
    *,
    shop_domain: str,
    webhook_id: str,
    topic: str,
    hmac_header: str | None,
    raw_body: bytes,
    payload: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    route, tenant = _resolve_route_and_tenant(db, channel="shopify", external_account_id=shop_domain.strip())
    if not hmac_header:
        raise HTTPException(status_code=401, detail="Missing X-Shopify-Hmac-Sha256 header")
    expected_b64 = base64.b64encode(
        hmac.new(route.app_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("ascii")
    if not hmac.compare_digest(expected_b64, hmac_header.strip()):
        raise HTTPException(status_code=401, detail="Invalid Shopify HMAC signature")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_commerce_ready(db, tenant)

    ext_order_id = str(payload.get("id") or "").strip() or None
    order_number = str(payload.get("order_number_ref") or payload.get("note") or "").strip() or None
    order = _locate_order_for_update(db, provider="shopify", external_order_id=ext_order_id, order_number=order_number)
    if order is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Matching Shopify commerce order not found")

    if ext_order_id and not order.external_order_id:
        order.external_order_id = ext_order_id

    currency = str(payload.get("currency") or order.currency).upper()[:3]
    amount_minor = int(payload.get("amount_minor") or 0)
    clean_topic = topic.strip().lower()
    ext_event_id = webhook_id.strip()[:160]

    if "refund" in clean_topic:
        order, duplicate = _apply_refund_in_tx(
            db,
            tenant,
            order,
            provider="shopify",
            external_event_id=ext_event_id,
            external_payment_id=ext_order_id,
            currency=currency,
            amount_minor=amount_minor,
            payload_json=payload,
            now=current,
        )
    elif "cancel" in clean_topic:
        existing_ev = db.scalar(
            select(CommercePaymentEvent).where(
                CommercePaymentEvent.provider == "shopify",
                CommercePaymentEvent.external_event_id == ext_event_id,
            )
        )
        duplicate = existing_ev is not None
        if not duplicate:
            order.status = "cancelled"
            order.updated_at = current
            db.add(
                CommercePaymentEvent(
                    order_id=order.id,
                    provider="shopify",
                    external_event_id=ext_event_id,
                    external_payment_id=ext_order_id,
                    event_type="payment_cancelled",
                    currency=order.currency,
                    amount_minor=0,
                    payload_json=payload,
                    occurred_at=current,
                    recorded_at=current,
                )
            )
    else:
        order, duplicate = _reconcile_payment_in_tx(
            db,
            tenant,
            order,
            provider="shopify",
            external_event_id=ext_event_id,
            external_payment_id=ext_order_id,
            currency=currency,
            amount_minor=amount_minor,
            payload_json=payload,
            now=current,
        )

    db.commit()
    db.refresh(order)
    res = _order_to_dict(order)
    res["duplicate"] = duplicate
    return res


def _parse_mercadopago_signature(header_value: str | None) -> tuple[str | None, str | None]:
    if not header_value:
        return None, None
    ts = None
    v1 = None
    for part in header_value.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k_clean = k.strip().lower()
        if k_clean == "ts":
            ts = v.strip()
        elif k_clean == "v1":
            v1 = v.strip()
    return ts, v1


def ingest_mercadopago_webhook(
    db: Session,
    *,
    account_id: str,
    x_signature: str | None,
    x_request_id: str | None,
    payload: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    route, tenant = _resolve_route_and_tenant(db, channel="mercadopago", external_account_id=account_id.strip())
    ts, v1 = _parse_mercadopago_signature(x_signature)
    data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    data_id = str(data_obj.get("id") or payload.get("id") or "").strip()
    if not ts or not v1 or not x_request_id or not data_id:
        raise HTTPException(status_code=401, detail="Invalid Mercado Pago x-signature headers")

    manifest = f"id:{data_id};request-id:{x_request_id.strip()};ts:{ts};"
    expected_v1 = hmac.new(route.app_secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_v1, v1):
        raise HTTPException(status_code=401, detail="Invalid Mercado Pago webhook signature")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_commerce_ready(db, tenant)

    ext_ref = str(payload.get("external_reference") or "").strip() or None
    ext_order_id = str(payload.get("merchant_order_id") or "").strip() or None
    order = _locate_order_for_update(db, provider="mercadopago", external_order_id=ext_order_id, order_number=ext_ref)
    if order is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Matching Mercado Pago commerce order not found")

    if ext_order_id and not order.external_order_id:
        order.external_order_id = ext_order_id

    status_name = str(payload.get("status") or "approved").strip().lower()
    currency = str(payload.get("currency_id") or order.currency).upper()[:3]
    amount_minor = int(payload.get("transaction_amount_minor") or 0)
    ext_event_id = x_request_id.strip()[:160]

    if status_name == "refunded":
        order, duplicate = _apply_refund_in_tx(
            db,
            tenant,
            order,
            provider="mercadopago",
            external_event_id=ext_event_id,
            external_payment_id=data_id,
            currency=currency,
            amount_minor=amount_minor,
            payload_json=payload,
            now=current,
        )
    elif status_name == "cancelled":
        existing_ev = db.scalar(
            select(CommercePaymentEvent).where(
                CommercePaymentEvent.provider == "mercadopago",
                CommercePaymentEvent.external_event_id == ext_event_id,
            )
        )
        duplicate = existing_ev is not None
        if not duplicate:
            order.status = "cancelled"
            order.updated_at = current
            db.add(
                CommercePaymentEvent(
                    order_id=order.id,
                    provider="mercadopago",
                    external_event_id=ext_event_id,
                    external_payment_id=data_id,
                    event_type="payment_cancelled",
                    currency=order.currency,
                    amount_minor=0,
                    payload_json=payload,
                    occurred_at=current,
                    recorded_at=current,
                )
            )
    else:
        order, duplicate = _reconcile_payment_in_tx(
            db,
            tenant,
            order,
            provider="mercadopago",
            external_event_id=ext_event_id,
            external_payment_id=data_id,
            currency=currency,
            amount_minor=amount_minor,
            payload_json=payload,
            now=current,
        )

    db.commit()
    db.refresh(order)
    res = _order_to_dict(order)
    res["duplicate"] = duplicate
    return res
