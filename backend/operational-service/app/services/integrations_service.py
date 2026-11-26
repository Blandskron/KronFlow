"""Meta omnichannel signed webhook ingestion, sync mappings, conflict reconciliation, and cursors."""

from datetime import datetime, timezone
import hashlib
import hmac
from typing import Any

from fastapi import HTTPException
from sqlalchemy import inspect, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext, ensure_runtime_is_usable
from app.public_models.channel_route import PublicChannelWebhookRoute
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.integrations import (
    ChannelWebhookRouteCreateIn,
    ExternalMappingResolveIn,
    ExternalMappingUpsertIn,
    SyncCursorUpsertIn,
)
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.lead_service import get_or_create_initial_lead
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.services.workflow_cancellation import cancel_waiting_runs_in_tx
from app.tenant_models.operations import Cliente, Conversation, Message
from app.tenant_models.phase5_integrations import ConnectorSyncCursor, ExternalEntityMapping


META_PROVIDER_BY_CHANNEL = {
    "whatsapp": "meta_whatsapp",
    "instagram": "meta_instagram",
    "messenger": "meta_messenger",
}
RECEIPT_RANK = {
    "unknown": 0,
    "received": 1,
    "sent": 2,
    "failed": 2,
    "delivered": 3,
    "read": 4,
}


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Integration timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _require_sync_ready(db: Session, tenant: TenantContext) -> None:
    inspector = inspect(db.connection())
    existing = set(inspector.get_table_names(schema=tenant.schema_name))
    if not {ExternalEntityMapping.__tablename__, ConnectorSyncCursor.__tablename__}.issubset(existing):
        raise HTTPException(status_code=503, detail="Integration sync schema is unavailable")


def _route_to_dict(route: PublicChannelWebhookRoute) -> dict[str, Any]:
    return {
        "id": route.id,
        "channel": route.channel,
        "provider": route.provider,
        "external_account_id": route.external_account_id,
        "connection_id": route.connection_id,
        "secret_fingerprint": route.secret_fingerprint,
        "is_active": route.is_active,
        "created_by": route.created_by,
        "created_at": route.created_at,
        "updated_at": route.updated_at,
    }


def _mapping_to_dict(row: ExternalEntityMapping) -> dict[str, Any]:
    return {
        "id": row.id,
        "connection_ref": row.connection_ref,
        "resource_type": row.resource_type,
        "remote_id": row.remote_id,
        "local_type": row.local_type,
        "local_id": row.local_id,
        "remote_version": row.remote_version,
        "local_version": row.local_version,
        "sync_state": row.sync_state,
        "conflict_payload": dict(row.conflict_payload or {}),
        "owner_user_id": row.owner_user_id,
        "last_synced_at": row.last_synced_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _cursor_to_dict(row: ConnectorSyncCursor) -> dict[str, Any]:
    return {
        "id": row.id,
        "connection_ref": row.connection_ref,
        "stream_name": row.stream_name,
        "cursor_value": row.cursor_value,
        "status": row.status,
        "last_error": row.last_error,
        "synced_count": row.synced_count,
        "updated_at": row.updated_at,
    }


def list_webhook_routes(db: Session, tenant: TenantContext) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(PublicChannelWebhookRoute)
            .where(PublicChannelWebhookRoute.auth_tenant_id == tenant.auth_tenant_id)
            .order_by(PublicChannelWebhookRoute.id.asc())
        ).all()
    )
    return [_route_to_dict(row) for row in rows]


def create_webhook_route(
    db: Session,
    tenant: TenantContext,
    payload: ChannelWebhookRouteCreateIn,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    provider = META_PROVIDER_BY_CHANNEL.get(payload.channel)
    if provider is None:
        raise HTTPException(status_code=422, detail="Unsupported channel")
    clean_account = payload.external_account_id.strip()[:128]
    if not clean_account:
        raise HTTPException(status_code=422, detail="external_account_id cannot be empty")
    existing = db.scalar(
        select(PublicChannelWebhookRoute).where(
            PublicChannelWebhookRoute.channel == payload.channel,
            PublicChannelWebhookRoute.external_account_id == clean_account,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Webhook route already registered for this external account")

    current = _now(now)
    route = PublicChannelWebhookRoute(
        auth_tenant_id=tenant.auth_tenant_id,
        channel=payload.channel,
        provider=provider,
        external_account_id=clean_account,
        connection_id=payload.connection_id,
        verify_token_hash=_sha256_hex(payload.verify_token.strip()),
        app_secret=payload.app_secret.strip(),
        secret_fingerprint=_sha256_hex(payload.app_secret.strip())[:32],
        is_active=True,
        created_by=actor_user_id[:64] if actor_user_id else None,
        created_at=current,
        updated_at=current,
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return _route_to_dict(route)


def deactivate_webhook_route(
    db: Session,
    tenant: TenantContext,
    route_id: int,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    route = db.scalar(
        select(PublicChannelWebhookRoute).where(
            PublicChannelWebhookRoute.id == route_id,
            PublicChannelWebhookRoute.auth_tenant_id == tenant.auth_tenant_id,
        )
    )
    if route is None:
        raise HTTPException(status_code=404, detail="Webhook route not found")
    route.is_active = False
    route.updated_at = _now(now)
    db.commit()
    db.refresh(route)
    return _route_to_dict(route)


def verify_meta_webhook_challenge(
    db: Session,
    *,
    channel: str,
    mode: str | None,
    verify_token: str | None,
    challenge: str | None,
) -> str:
    if channel not in META_PROVIDER_BY_CHANNEL:
        raise HTTPException(status_code=404, detail="Unsupported Meta webhook channel")
    if mode != "subscribe" or not verify_token or not challenge:
        raise HTTPException(status_code=403, detail="Invalid Meta webhook verification challenge")
    candidate_hash = _sha256_hex(verify_token.strip())
    routes = list(
        db.scalars(
            select(PublicChannelWebhookRoute).where(
                PublicChannelWebhookRoute.channel == channel,
                PublicChannelWebhookRoute.is_active.is_(True),
            )
        ).all()
    )
    for route in routes:
        if hmac.compare_digest(route.verify_token_hash, candidate_hash):
            return challenge
    raise HTTPException(status_code=403, detail="Meta verify token rejected")


def _extract_meta_events(channel: str, payload: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    entries = payload.get("entry")
    if not isinstance(entries, list) or not entries:
        return None, [], []

    account_id: str | None = None
    inbound: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if channel == "whatsapp":
            for change in entry.get("changes") or []:
                if not isinstance(change, dict):
                    continue
                val = change.get("value") or {}
                if not isinstance(val, dict):
                    continue
                meta = val.get("metadata") or {}
                if isinstance(meta, dict) and meta.get("phone_number_id"):
                    account_id = account_id or str(meta["phone_number_id"])
                names_by_wa: dict[str, str] = {}
                for c in val.get("contacts") or []:
                    if isinstance(c, dict) and c.get("wa_id"):
                        prof = c.get("profile") or {}
                        names_by_wa[str(c["wa_id"])] = str(prof.get("name") or "") if isinstance(prof, dict) else ""
                for msg in val.get("messages") or []:
                    if not isinstance(msg, dict) or not msg.get("id") or not msg.get("from"):
                        continue
                    sender = str(msg["from"])
                    text_obj = msg.get("text") or {}
                    body = str(text_obj.get("body") or "") if isinstance(text_obj, dict) else ""
                    inbound.append(
                        {
                            "external_message_id": str(msg["id"]),
                            "sender_id": sender,
                            "sender_name": names_by_wa.get(sender) or sender,
                            "body": body or "[media]",
                        }
                    )
                for st in val.get("statuses") or []:
                    if isinstance(st, dict) and st.get("id") and st.get("status"):
                        receipts.append({"external_message_id": str(st["id"]), "status": str(st["status"]).lower()})
        else:
            if entry.get("id"):
                account_id = account_id or str(entry["id"])
            for ev in entry.get("messaging") or []:
                if not isinstance(ev, dict):
                    continue
                sender = ev.get("sender") or {}
                sender_id = str(sender.get("id") or "") if isinstance(sender, dict) else ""
                msg = ev.get("message")
                if isinstance(msg, dict) and msg.get("mid") and sender_id and not msg.get("is_echo"):
                    inbound.append(
                        {
                            "external_message_id": str(msg["mid"]),
                            "sender_id": sender_id,
                            "sender_name": sender_id,
                            "body": str(msg.get("text") or "[media]"),
                        }
                    )
                delivery = ev.get("delivery")
                if isinstance(delivery, dict):
                    for mid in delivery.get("mids") or []:
                        receipts.append({"external_message_id": str(mid), "status": "delivered"})
                read = ev.get("read")
                if isinstance(read, dict) and read.get("mid"):
                    receipts.append({"external_message_id": str(read["mid"]), "status": "read"})

    return account_id, inbound, receipts


def ingest_meta_webhook(
    db: Session,
    *,
    channel: str,
    raw_body: bytes,
    signature_header: str | None,
    payload: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    if channel not in META_PROVIDER_BY_CHANNEL:
        raise HTTPException(status_code=404, detail="Unsupported Meta webhook channel")

    account_id, inbound_items, receipt_items = _extract_meta_events(channel, payload)
    if not account_id:
        raise HTTPException(status_code=422, detail="Unable to determine external account id from Meta payload")

    route = db.scalar(
        select(PublicChannelWebhookRoute).where(
            PublicChannelWebhookRoute.channel == channel,
            PublicChannelWebhookRoute.external_account_id == account_id,
            PublicChannelWebhookRoute.is_active.is_(True),
        )
    )
    if route is None:
        raise HTTPException(status_code=404, detail="Webhook route not found or inactive")

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

    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")
    expected_sig = "sha256=" + hmac.new(route.app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, signature_header.strip()):
        raise HTTPException(status_code=401, detail="Invalid Meta webhook signature")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    conn_scope = f"{route.provider}:{route.external_account_id}"
    inspector = inspect(db.connection())
    sync_ready = inspector.has_table(ExternalEntityMapping.__tablename__, schema=tenant.schema_name)

    ingested = 0
    duplicates = 0
    receipts_updated = 0

    for item in inbound_items:
        ext_msg_id = item["external_message_id"][:220]
        existing = db.scalar(
            select(Message.id).where(
                Message.connection_id == conn_scope,
                Message.channel == channel,
                Message.external_message_id == ext_msg_id,
            )
        )
        if existing is not None:
            duplicates += 1
            continue

        sender_id = item["sender_id"][:120]
        scoped_thread = f"{channel}:{route.external_account_id}:{sender_id}"

        cliente: Cliente | None = None
        if sync_ready:
            mapping = db.scalar(
                select(ExternalEntityMapping).where(
                    ExternalEntityMapping.connection_ref == conn_scope,
                    ExternalEntityMapping.resource_type == "contact",
                    ExternalEntityMapping.remote_id == sender_id,
                )
            )
            if mapping is not None and mapping.local_id.isdigit():
                cliente = db.get(Cliente, int(mapping.local_id))

        if cliente is None:
            cliente = db.scalar(select(Cliente).where(Cliente.whatsapp_id == scoped_thread))
        if cliente is None:
            cliente = Cliente(
                rut=f"{channel[:2]}:{route.external_account_id}:{sender_id}"[:64],
                nombre=item["sender_name"][:180] or sender_id,
                whatsapp_id=scoped_thread,
                canal_origen=channel,
                consentimiento_datos=True,
                fecha_consentimiento=current,
            )
            db.add(cliente)
            db.flush()

        if sync_ready:
            db.execute(
                insert(ExternalEntityMapping)
                .values(
                    connection_ref=conn_scope,
                    resource_type="contact",
                    remote_id=sender_id,
                    local_type="contact",
                    local_id=str(cliente.id),
                    local_version=1,
                    sync_state="synced",
                    conflict_payload={},
                    last_synced_at=current,
                    created_at=current,
                    updated_at=current,
                )
                .on_conflict_do_nothing(index_elements=["connection_ref", "resource_type", "remote_id"])
            )

        lead, lead_created = get_or_create_initial_lead(db, cliente.id)
        if lead_created:
            publish_domain_event_in_tx(
                db,
                tenant,
                event_type="lead.created",
                aggregate_type="lead",
                aggregate_id=lead.id,
                payload={"lead_id": lead.id, "contact_id": cliente.id, "channel": channel},
                occurred_at=current,
            )

        conv = db.scalar(select(Conversation).where(Conversation.session_id == scoped_thread))
        if conv is None:
            conv = Conversation(
                session_id=scoped_thread,
                message={"channel": channel, "external_account_id": route.external_account_id, "sender_id": sender_id},
            )
            db.add(conv)
            db.flush()

        msg = Message(
            whatsapp_id=scoped_thread,
            rol="usuario",
            mensaje=item["body"],
            creado_en=current,
            connection_id=conn_scope,
            channel=channel,
            external_message_id=ext_msg_id,
            provider_message_id=ext_msg_id,
            direction="inbound",
            message_type="text",
            delivery_status="received",
        )
        db.add(msg)
        db.flush()

        publish_domain_event_in_tx(
            db,
            tenant,
            event_type="message.inbound.received",
            aggregate_type="conversation",
            aggregate_id=conv.id,
            payload={
                "conversation_id": conv.id,
                "contact_id": cliente.id,
                "lead_id": lead.id,
                "channel": channel,
                "external_account_id": route.external_account_id,
                "message_id": ext_msg_id,
            },
            occurred_at=current,
        )
        cancel_waiting_runs_in_tx(
            db,
            tenant,
            event_type="message.inbound.received",
            contact_id=cliente.id,
            conversation_id=conv.id,
            reason="customer_replied",
            now=current,
        )
        ingested += 1

    for rcpt in receipt_items:
        target_status = rcpt["status"]
        new_rank = RECEIPT_RANK.get(target_status)
        if new_rank is None:
            continue
        ext_id = rcpt["external_message_id"][:220]
        msg = db.scalar(
            select(Message).where(
                Message.connection_id == conn_scope,
                or_(Message.provider_message_id == ext_id, Message.external_message_id == ext_id),
            )
        )
        if msg is not None and new_rank > RECEIPT_RANK.get(msg.delivery_status, 0):
            msg.delivery_status = target_status
            receipts_updated += 1

    db.commit()
    return {
        "channel": channel,
        "external_account_id": route.external_account_id,
        "ingested": ingested,
        "duplicates": duplicates,
        "receipts_updated": receipts_updated,
    }


def list_external_mappings(
    db: Session,
    tenant: TenantContext,
    *,
    sync_state: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    _require_sync_ready(db, tenant)
    stmt = select(ExternalEntityMapping).order_by(ExternalEntityMapping.id.desc()).limit(max(1, min(limit, 100)))
    if sync_state:
        stmt = stmt.where(ExternalEntityMapping.sync_state == sync_state.strip())
    return [_mapping_to_dict(row) for row in db.scalars(stmt).all()]


def upsert_external_mapping(
    db: Session,
    tenant: TenantContext,
    payload: ExternalMappingUpsertIn,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_sync_ready(db, tenant)
    conn_ref = payload.connection_ref.strip()[:80]
    res_type = payload.resource_type.strip()[:32]
    remote_id = payload.remote_id.strip()[:160]

    row = db.scalar(
        select(ExternalEntityMapping)
        .where(
            ExternalEntityMapping.connection_ref == conn_ref,
            ExternalEntityMapping.resource_type == res_type,
            ExternalEntityMapping.remote_id == remote_id,
        )
        .with_for_update()
    )
    if row is None:
        row = ExternalEntityMapping(
            connection_ref=conn_ref,
            resource_type=res_type,
            remote_id=remote_id,
            local_type=payload.local_type.strip()[:32],
            local_id=payload.local_id.strip()[:64],
            remote_version=payload.remote_version,
            local_version=1,
            sync_state="synced",
            conflict_payload={},
            owner_user_id=actor_user_id[:64] if actor_user_id else None,
            last_synced_at=current,
            created_at=current,
            updated_at=current,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _mapping_to_dict(row)

    if payload.expected_local_version is not None and row.local_version != payload.expected_local_version:
        row.sync_state = "conflict"
        row.conflict_payload = {
            "expected_local_version": payload.expected_local_version,
            "actual_local_version": row.local_version,
            "incoming_local_id": payload.local_id,
            "incoming_remote_version": payload.remote_version,
            "incoming_payload": dict(payload.payload or {}),
        }
        row.owner_user_id = actor_user_id[:64] if actor_user_id else row.owner_user_id
        row.updated_at = current
        publish_domain_event_in_tx(
            db,
            tenant,
            event_type="integration.mapping.conflict",
            aggregate_type="external_mapping",
            aggregate_id=row.id,
            payload={"connection_ref": conn_ref, "resource_type": res_type, "remote_id": remote_id},
            occurred_at=current,
        )
        create_system_event(
            db,
            "integration.mapping.conflict",
            tenant.auth_tenant_id,
            tenant.schema_name,
            {"mapping_id": row.id, "connection_ref": conn_ref, "remote_id": remote_id},
        )
        db.commit()
        db.refresh(row)
        return _mapping_to_dict(row)

    row.local_type = payload.local_type.strip()[:32]
    row.local_id = payload.local_id.strip()[:64]
    row.remote_version = payload.remote_version
    row.local_version += 1
    row.sync_state = "synced"
    row.conflict_payload = {}
    row.last_synced_at = current
    row.updated_at = current
    db.commit()
    db.refresh(row)
    return _mapping_to_dict(row)


def resolve_external_mapping_conflict(
    db: Session,
    tenant: TenantContext,
    mapping_id: int,
    payload: ExternalMappingResolveIn,
    *,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_sync_ready(db, tenant)
    row = db.scalar(select(ExternalEntityMapping).where(ExternalEntityMapping.id == mapping_id).with_for_update())
    if row is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="External mapping not found")

    if payload.local_id is not None:
        row.local_id = payload.local_id.strip()[:64]
    if payload.remote_version is not None:
        row.remote_version = payload.remote_version
    row.sync_state = payload.resolution
    row.conflict_payload = {}
    row.owner_user_id = actor_user_id[:64]
    row.local_version += 1
    row.last_synced_at = current
    row.updated_at = current

    create_system_event(
        db,
        "integration.mapping.resolved",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"mapping_id": row.id, "resolution": payload.resolution, "resolved_by": actor_user_id},
    )
    db.commit()
    db.refresh(row)
    return _mapping_to_dict(row)


def upsert_sync_cursor(
    db: Session,
    tenant: TenantContext,
    payload: SyncCursorUpsertIn,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_sync_ready(db, tenant)
    conn_ref = payload.connection_ref.strip()[:80]
    stream = payload.stream_name.strip()[:64]
    db.execute(
        insert(ConnectorSyncCursor)
        .values(
            connection_ref=conn_ref,
            stream_name=stream,
            cursor_value=payload.cursor_value.strip()[:255],
            status=payload.status,
            last_error=payload.last_error.strip()[:300] if payload.last_error else None,
            synced_count=payload.synced_count,
            updated_at=current,
        )
        .on_conflict_do_update(
            index_elements=["connection_ref", "stream_name"],
            set_={
                "cursor_value": payload.cursor_value.strip()[:255],
                "status": payload.status,
                "last_error": payload.last_error.strip()[:300] if payload.last_error else None,
                "synced_count": payload.synced_count,
                "updated_at": current,
            },
        )
    )
    db.commit()
    row = db.scalar(
        select(ConnectorSyncCursor).where(
            ConnectorSyncCursor.connection_ref == conn_ref,
            ConnectorSyncCursor.stream_name == stream,
        )
    )
    return _cursor_to_dict(row)


def list_sync_cursors(db: Session, tenant: TenantContext) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    _require_sync_ready(db, tenant)
    rows = list(db.scalars(select(ConnectorSyncCursor).order_by(ConnectorSyncCursor.id.asc())).all())
    return [_cursor_to_dict(row) for row in rows]
