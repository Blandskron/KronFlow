"""Outbound reference connectors: WhatsApp Cloud API, Google Calendar OAuth sync, and HubSpot CRM sync."""

from datetime import datetime, timezone
import json
from typing import Any, Callable
import urllib.error
from urllib.parse import urlencode
import urllib.request

from fastapi import HTTPException
from sqlalchemy import inspect, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.connectors import (
    GoogleCalendarPushIn,
    GoogleCalendarSyncIn,
    HubSpotSyncIn,
    WhatsAppCloudSendIn,
)
from app.services.post_v1_service import _validate_webhook_url
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.consent_ledger import ContactSuppression
from app.tenant_models.operations import Cliente, Message
from app.tenant_models.opportunity import Opportunity
from app.tenant_models.phase5_integrations import ConnectorSyncCursor, ExternalEntityMapping
from app.tenant_models.post_v1 import CalendarAppointment


HttpTransport = Callable[
    [str, str, dict[str, str], dict[str, Any] | None],
    tuple[int, dict[str, str], dict[str, Any]],
]


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Connector timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _default_http_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any] | None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    _validate_webhook_url(url)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req_headers = {"Accept": "application/json", **headers}
    if data is not None:
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            parsed = json.loads(raw)
            return int(resp.status), dict(resp.headers.items()), parsed if isinstance(parsed, dict) else {"raw": parsed}
    except urllib.error.HTTPError as exc:
        raw_err = exc.read().decode("utf-8", errors="ignore") if exc.fp else "{}"
        try:
            parsed_err = json.loads(raw_err)
        except json.JSONDecodeError:
            parsed_err = {"error": raw_err}
        return int(exc.code), dict(exc.headers.items()), parsed_err if isinstance(parsed_err, dict) else {}
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"Connector HTTP transport failed: {exc}") from None


def _upsert_cursor_in_tx(
    db: Session,
    *,
    connection_ref: str,
    stream_name: str,
    cursor_value: str,
    status: str,
    last_error: str | None,
    synced_count: int,
    now: datetime,
) -> None:
    db.execute(
        insert(ConnectorSyncCursor)
        .values(
            connection_ref=connection_ref[:80],
            stream_name=stream_name[:64],
            cursor_value=cursor_value[:255],
            status=status,
            last_error=last_error[:300] if last_error else None,
            synced_count=max(0, synced_count),
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["connection_ref", "stream_name"],
            set_={
                "cursor_value": cursor_value[:255],
                "status": status,
                "last_error": last_error[:300] if last_error else None,
                "synced_count": max(0, synced_count),
                "updated_at": now,
            },
        )
    )


def send_whatsapp_cloud_message(
    db: Session,
    tenant: TenantContext,
    payload: WhatsAppCloudSendIn,
    *,
    actor_user_id: str,
    transport: HttpTransport | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)

    if payload.outside_24h_window and not (payload.template_name and payload.template_name.strip()):
        raise HTTPException(
            status_code=422,
            detail="Approved template_name is required outside the 24h WhatsApp customer service window",
        )
    if not (payload.body_text and payload.body_text.strip()) and not (payload.template_name and payload.template_name.strip()):
        raise HTTPException(status_code=422, detail="Either body_text or template_name is required")

    norm_to = payload.to_phone.strip()
    existing_tables = set(inspect(db.connection()).get_table_names(schema=tenant.schema_name))
    if ContactSuppression.__tablename__ in existing_tables:
        sup_filters = [ContactSuppression.destination == norm_to]
        if payload.client_id is not None:
            sup_filters.append(ContactSuppression.client_id == payload.client_id)
        suppressed = db.scalar(
            select(ContactSuppression.id).where(ContactSuppression.channel == "whatsapp", or_(*sup_filters)).limit(1)
        )
        if suppressed is not None:
            raise HTTPException(status_code=403, detail="Recipient is suppressed for WhatsApp outbound messaging")

    conn_scope = f"meta_whatsapp:{payload.phone_number_id.strip()}"[:80]
    idem = payload.idempotency_key.strip()[:220]
    existing_msg = db.scalar(
        select(Message).where(
            Message.connection_id == conn_scope,
            Message.channel == "whatsapp",
            Message.external_message_id == idem,
        )
    )
    if existing_msg is not None:
        return {
            "duplicate": True,
            "message_id": existing_msg.id,
            "provider_message_id": existing_msg.provider_message_id,
            "connection_id": conn_scope,
            "status": existing_msg.delivery_status,
        }

    url = f"https://graph.facebook.com/v21.0/{payload.phone_number_id.strip()}/messages"
    graph_body: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": norm_to,
    }
    if payload.template_name and payload.template_name.strip():
        graph_body["type"] = "template"
        graph_body["template"] = {
            "name": payload.template_name.strip(),
            "language": {"code": payload.template_language.strip()},
        }
        visible_text = f"[template:{payload.template_name.strip()}]"
    else:
        graph_body["type"] = "text"
        visible_text = payload.body_text.strip()
        graph_body["text"] = {"body": visible_text}

    headers = {"Authorization": f"Bearer {payload.access_token.strip()}"} if payload.access_token else {}
    sender = transport or _default_http_transport
    status_code, _, res_body = sender("POST", url, headers, graph_body)
    if status_code < 200 or status_code >= 300:
        raise HTTPException(status_code=502, detail=f"WhatsApp Cloud API returned HTTP {status_code}")

    msgs = res_body.get("messages") if isinstance(res_body.get("messages"), list) else []
    provider_msg_id = str(msgs[0].get("id")) if msgs and isinstance(msgs[0], dict) and msgs[0].get("id") else f"wamid.out:{idem}"

    msg = Message(
        whatsapp_id=norm_to,
        rol="agente",
        mensaje=visible_text,
        creado_en=current,
        connection_id=conn_scope,
        channel="whatsapp",
        external_message_id=idem,
        provider_message_id=provider_msg_id[:220],
        direction="outbound",
        message_type="template" if payload.template_name else "text",
        delivery_status="sent",
    )
    db.add(msg)
    db.flush()
    create_system_event(
        db,
        "connector.whatsapp_cloud.sent",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"message_id": msg.id, "provider_message_id": msg.provider_message_id, "actor_user_id": actor_user_id},
    )
    db.commit()
    db.refresh(msg)
    return {
        "duplicate": False,
        "message_id": msg.id,
        "provider_message_id": msg.provider_message_id,
        "connection_id": conn_scope,
        "status": msg.delivery_status,
    }


def push_appointment_to_google_calendar(
    db: Session,
    tenant: TenantContext,
    appointment_id: int,
    payload: GoogleCalendarPushIn,
    *,
    actor_user_id: str,
    transport: HttpTransport | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    appt = db.get(CalendarAppointment, appointment_id)
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    cal_id = payload.calendar_id.strip()
    conn_ref = f"google_calendar:{cal_id}"[:80]
    mapping = db.scalar(
        select(ExternalEntityMapping).where(
            ExternalEntityMapping.connection_ref == conn_ref,
            ExternalEntityMapping.resource_type == "appointment",
            ExternalEntityMapping.local_type == "appointment",
            ExternalEntityMapping.local_id == str(appt.id),
        )
    )

    sender = transport or _default_http_transport
    headers = {"Authorization": f"Bearer {payload.access_token.strip()}"} if payload.access_token else {}
    event_body = {
        "summary": appt.title,
        "start": {"dateTime": appt.starts_at.isoformat()},
        "end": {"dateTime": appt.ends_at.isoformat()},
        "status": "cancelled" if appt.status == "cancelled" else "confirmed",
    }

    if mapping is None:
        url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
        code, _, res = sender("POST", url, headers, event_body)
        if code < 200 or code >= 300:
            raise HTTPException(status_code=502, detail=f"Google Calendar push returned HTTP {code}")
        remote_id = str(res.get("id") or f"gcal_{appt.id}")
        remote_etag = str(res.get("etag") or "v1")
        mapping = ExternalEntityMapping(
            connection_ref=conn_ref,
            resource_type="appointment",
            remote_id=remote_id[:160],
            local_type="appointment",
            local_id=str(appt.id),
            remote_version=remote_etag[:64],
            local_version=1,
            sync_state="synced",
            conflict_payload={},
            owner_user_id=actor_user_id[:64],
            last_synced_at=current,
            created_at=current,
            updated_at=current,
        )
        db.add(mapping)
    else:
        url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events/{mapping.remote_id}"
        code, _, res = sender("PATCH", url, headers, event_body)
        if code < 200 or code >= 300:
            raise HTTPException(status_code=502, detail=f"Google Calendar update returned HTTP {code}")
        mapping.remote_version = str(res.get("etag") or mapping.remote_version or "v2")[:64]
        mapping.local_version += 1
        mapping.sync_state = "synced"
        mapping.last_synced_at = current
        mapping.updated_at = current

    db.commit()
    db.refresh(mapping)
    return {
        "appointment_id": appt.id,
        "calendar_id": cal_id,
        "remote_event_id": mapping.remote_id,
        "sync_state": mapping.sync_state,
    }


def sync_google_calendar_events(
    db: Session,
    tenant: TenantContext,
    payload: GoogleCalendarSyncIn,
    *,
    actor_user_id: str,
    transport: HttpTransport | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    cal_id = payload.calendar_id.strip()
    conn_ref = f"google_calendar:{cal_id}"[:80]

    cursor_row = db.scalar(
        select(ConnectorSyncCursor).where(
            ConnectorSyncCursor.connection_ref == conn_ref,
            ConnectorSyncCursor.stream_name == "events",
        )
    )
    sync_token = None if payload.force_full_resync or cursor_row is None else cursor_row.cursor_value

    sender = transport or _default_http_transport
    headers = {"Authorization": f"Bearer {payload.access_token.strip()}"} if payload.access_token else {}
    base_url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"

    cursor_reset = False
    query = urlencode({"syncToken": sync_token}) if sync_token else ""
    code, _, res = sender("GET", f"{base_url}?{query}" if query else base_url, headers, None)
    if code == 410:
        # Lost/expired syncToken: drop stale cursor and rebuild projection cleanly without losing local bookings.
        cursor_reset = True
        code, _, res = sender("GET", base_url, headers, None)

    if code < 200 or code >= 300:
        raise HTTPException(status_code=502, detail=f"Google Calendar sync returned HTTP {code}")

    items = res.get("items") if isinstance(res.get("items"), list) else []
    synced = 0
    for ev in items:
        if not isinstance(ev, dict) or not ev.get("id"):
            continue
        remote_id = str(ev["id"])
        mapping = db.scalar(
            select(ExternalEntityMapping).where(
                ExternalEntityMapping.connection_ref == conn_ref,
                ExternalEntityMapping.resource_type == "appointment",
                ExternalEntityMapping.remote_id == remote_id,
            )
        )
        if mapping is not None and str(ev.get("status") or "").lower() == "cancelled" and mapping.local_id.isdigit():
            appt = db.get(CalendarAppointment, int(mapping.local_id))
            if appt is not None:
                appt.status = "cancelled"
                appt.updated_at = current
            mapping.local_version += 1
            mapping.last_synced_at = current
            mapping.updated_at = current
        synced += 1

    next_token = str(res.get("nextSyncToken") or f"sync_{int(current.timestamp())}")
    _upsert_cursor_in_tx(
        db,
        connection_ref=conn_ref,
        stream_name="events",
        cursor_value=next_token,
        status="ok",
        last_error=None,
        synced_count=synced,
        now=current,
    )
    create_system_event(
        db,
        "connector.google_calendar.synced",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"calendar_id": cal_id, "synced": synced, "cursor_reset": cursor_reset, "actor_user_id": actor_user_id},
    )
    db.commit()
    return {
        "provider": "google_calendar",
        "stream": "events",
        "status": "ok",
        "synced": synced,
        "conflicts": 0,
        "cursor_reset": cursor_reset,
        "rate_limited": False,
        "cursor_value": next_token,
        "updated_at": current,
    }


def sync_hubspot_crm(
    db: Session,
    tenant: TenantContext,
    payload: HubSpotSyncIn,
    *,
    actor_user_id: str,
    transport: HttpTransport | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    conn_ref = "hubspot"

    if payload.stream == "contacts":
        rows = list(db.scalars(select(Cliente).order_by(Cliente.id.asc()).limit(payload.batch_size)).all())
        records = [
            {
                "id": str(c.id),
                "properties": {"email": c.email or "", "firstname": c.nombre, "phone": c.telefono or ""},
            }
            for c in rows
        ]
        url = "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert"
        resource_type = "contact"
    else:
        rows = list(db.scalars(select(Opportunity).order_by(Opportunity.id.asc()).limit(payload.batch_size)).all())
        records = [
            {
                "id": str(o.id),
                "properties": {"dealname": o.title, "amount": str(o.amount), "pipeline": o.outcome},
            }
            for o in rows
        ]
        url = "https://api.hubapi.com/crm/v3/objects/deals/batch/upsert"
        resource_type = "opportunity"

    headers = {"Authorization": f"Bearer {payload.access_token.strip()}"} if payload.access_token else {}
    sender = transport or _default_http_transport
    code, resp_headers, res_body = sender("POST", url, headers, {"inputs": records})

    if code == 429:
        raw_retry = resp_headers.get("Retry-After") or resp_headers.get("retry-after") or "60"
        try:
            retry_after = max(1, int(raw_retry))
        except ValueError:
            retry_after = 60
        _upsert_cursor_in_tx(
            db,
            connection_ref=conn_ref,
            stream_name=payload.stream,
            cursor_value=f"paused_at:{int(current.timestamp())}",
            status="paused",
            last_error=f"rate_limited:retry_after={retry_after}",
            synced_count=0,
            now=current,
        )
        db.commit()
        return {
            "provider": "hubspot",
            "stream": payload.stream,
            "status": "paused",
            "synced": 0,
            "conflicts": 0,
            "rate_limited": True,
            "retry_after_seconds": retry_after,
            "updated_at": current,
        }

    if code < 200 or code >= 300:
        raise HTTPException(status_code=502, detail=f"HubSpot CRM sync returned HTTP {code}")

    results = res_body.get("results") if isinstance(res_body.get("results"), list) else []
    synced = 0
    conflicts = 0
    for item in results:
        if not isinstance(item, dict) or not item.get("id") or not item.get("local_id"):
            continue
        remote_id = str(item["id"])
        local_id = str(item["local_id"])
        remote_ver = str(item.get("version") or "1")[:64]
        existing = db.scalar(
            select(ExternalEntityMapping).where(
                ExternalEntityMapping.connection_ref == conn_ref,
                ExternalEntityMapping.resource_type == resource_type,
                ExternalEntityMapping.remote_id == remote_id,
            )
        )
        if existing is None:
            db.add(
                ExternalEntityMapping(
                    connection_ref=conn_ref,
                    resource_type=resource_type,
                    remote_id=remote_id[:160],
                    local_type=resource_type,
                    local_id=local_id[:64],
                    remote_version=remote_ver,
                    local_version=1,
                    sync_state="synced",
                    conflict_payload={},
                    owner_user_id=actor_user_id[:64],
                    last_synced_at=current,
                    created_at=current,
                    updated_at=current,
                )
            )
            synced += 1
        elif bool(item.get("conflict")):
            existing.sync_state = "conflict"
            existing.conflict_payload = {"remote_version": remote_ver, "incoming_local_id": local_id}
            existing.updated_at = current
            conflicts += 1
        else:
            existing.remote_version = remote_ver
            existing.local_version += 1
            existing.sync_state = "synced"
            existing.last_synced_at = current
            existing.updated_at = current
            synced += 1

    cursor_val = str(res_body.get("cursor") or f"hs_{int(current.timestamp())}")
    _upsert_cursor_in_tx(
        db,
        connection_ref=conn_ref,
        stream_name=payload.stream,
        cursor_value=cursor_val,
        status="ok",
        last_error=None,
        synced_count=synced,
        now=current,
    )
    db.commit()
    return {
        "provider": "hubspot",
        "stream": payload.stream,
        "status": "ok",
        "synced": synced,
        "conflicts": conflicts,
        "cursor_reset": False,
        "rate_limited": False,
        "cursor_value": cursor_val,
        "updated_at": current,
    }
