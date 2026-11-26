"""Embeddable signed webchat widget management, visitor sessions, cursor polling, and HITL continuity."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from typing import Any
import urllib.error
import urllib.request
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limit import IngestRateLimiter
from app.core.tenant_resolver import TenantContext, ensure_runtime_is_usable
from app.public_models.tenant_runtime import TenantRuntime
from app.public_models.webchat import PublicWebchatWidget
from app.schemas.webchat import WebchatWidgetCreateIn, WebchatWidgetUpdateIn
from app.services.contact_points import normalize_email
from app.services.conversation_control_service import (
    get_conversation_control,
    is_ai_permitted_for_conversation_in_tx,
)
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.lead_service import get_or_create_initial_lead
from app.services.tenant_data import bind_tenant_session
from app.services.workflow_cancellation import cancel_waiting_runs_in_tx
from app.tenant_models.context import TenantAgentProfile
from app.tenant_models.operations import Cliente, Conversation, Message
from app.tenant_models.phase4_hub import WebchatSession


_WEBCHAT_LIMITER: IngestRateLimiter | None = None


def _get_limiter() -> IngestRateLimiter:
    global _WEBCHAT_LIMITER
    if _WEBCHAT_LIMITER is None:
        _WEBCHAT_LIMITER = IngestRateLimiter(get_settings().redis_url, window_seconds=60)
    return _WEBCHAT_LIMITER


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Webchat timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def normalize_webchat_origin(raw_origin: str) -> str:
    candidate = (raw_origin or "").strip()
    if not candidate or "*" in candidate:
        raise HTTPException(status_code=422, detail="Origin cannot be empty or contain wildcards")
    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https") or not parsed.netloc or not parsed.hostname:
        raise HTTPException(status_code=422, detail=f"Invalid webchat origin: '{raw_origin}'")
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise HTTPException(status_code=422, detail=f"Origin must only contain scheme and host[:port]: '{raw_origin}'")
    if parsed.path not in ("", "/"):
        raise HTTPException(status_code=422, detail=f"Origin must not include a path: '{raw_origin}'")
    return f"{scheme}://{parsed.netloc.lower()}"


def validate_allowed_origins(origins: list[str]) -> list[str]:
    if not origins:
        raise HTTPException(status_code=422, detail="At least one allowed origin is required")
    seen: list[str] = []
    for item in origins:
        norm = normalize_webchat_origin(item)
        if norm not in seen:
            seen.append(norm)
    return seen


def _require_webchat_ready(db: Session, tenant: TenantContext) -> None:
    inspector = inspect(db.connection())
    if not inspector.has_table(WebchatSession.__tablename__, schema=tenant.schema_name):
        raise HTTPException(status_code=503, detail="Webchat schema is unavailable")


def _widget_to_dict(widget: PublicWebchatWidget) -> dict[str, Any]:
    return {
        "id": widget.id,
        "widget_key": widget.widget_key,
        "name": widget.name,
        "is_active": widget.is_active,
        "allowed_origins": list(widget.allowed_origins or []),
        "agent_id": widget.agent_id,
        "welcome_message": widget.welcome_message,
        "session_ttl_minutes": widget.session_ttl_minutes,
        "rate_limit_per_minute": widget.rate_limit_per_minute,
        "created_by": widget.created_by,
        "created_at": widget.created_at,
        "updated_at": widget.updated_at,
    }


def _msg_to_dict(msg: Message) -> dict[str, Any]:
    return {
        "id": msg.id,
        "direction": msg.direction,
        "sender_role": msg.rol,
        "body": msg.mensaje,
        "delivery_status": msg.delivery_status,
        "created_at": msg.creado_en,
    }


def list_webchat_widgets(db: Session, tenant: TenantContext) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(PublicWebchatWidget)
            .where(PublicWebchatWidget.auth_tenant_id == tenant.auth_tenant_id)
            .order_by(PublicWebchatWidget.id.asc())
        ).all()
    )
    return [_widget_to_dict(row) for row in rows]


def create_webchat_widget(
    db: Session,
    tenant: TenantContext,
    payload: WebchatWidgetCreateIn,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    origins = validate_allowed_origins(payload.allowed_origins)
    current = _now(now)
    if payload.agent_id is not None:
        bind_tenant_session(db, tenant.schema_name)
        if db.get(TenantAgentProfile, payload.agent_id) is None:
            raise HTTPException(status_code=404, detail="Assigned agent not found")

    widget = PublicWebchatWidget(
        auth_tenant_id=tenant.auth_tenant_id,
        widget_key=f"wc_{secrets.token_urlsafe(18)}",
        name=payload.name.strip()[:160],
        is_active=bool(payload.is_active),
        allowed_origins=origins,
        agent_id=payload.agent_id,
        welcome_message=payload.welcome_message.strip()[:300],
        session_ttl_minutes=payload.session_ttl_minutes,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        created_by=actor_user_id[:64] if actor_user_id else None,
        created_at=current,
        updated_at=current,
    )
    db.add(widget)
    db.commit()
    db.refresh(widget)
    return _widget_to_dict(widget)


def update_webchat_widget(
    db: Session,
    tenant: TenantContext,
    widget_id: int,
    payload: WebchatWidgetUpdateIn,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    widget = db.scalar(
        select(PublicWebchatWidget).where(
            PublicWebchatWidget.id == widget_id,
            PublicWebchatWidget.auth_tenant_id == tenant.auth_tenant_id,
        )
    )
    if widget is None:
        raise HTTPException(status_code=404, detail="Webchat widget not found")

    current = _now(now)
    if payload.name is not None:
        widget.name = payload.name.strip()[:160]
    if payload.allowed_origins is not None:
        widget.allowed_origins = validate_allowed_origins(payload.allowed_origins)
    if payload.agent_id is not None:
        bind_tenant_session(db, tenant.schema_name)
        if db.get(TenantAgentProfile, payload.agent_id) is None:
            raise HTTPException(status_code=404, detail="Assigned agent not found")
        widget.agent_id = payload.agent_id
    if payload.welcome_message is not None:
        widget.welcome_message = payload.welcome_message.strip()[:300]
    if payload.session_ttl_minutes is not None:
        widget.session_ttl_minutes = payload.session_ttl_minutes
    if payload.rate_limit_per_minute is not None:
        widget.rate_limit_per_minute = payload.rate_limit_per_minute
    if payload.is_active is not None:
        widget.is_active = bool(payload.is_active)
    widget.updated_at = current
    db.commit()
    db.refresh(widget)
    return _widget_to_dict(widget)


def _resolve_active_widget_and_tenant(db: Session, widget_key: str) -> tuple[PublicWebchatWidget, TenantContext]:
    widget = db.scalar(select(PublicWebchatWidget).where(PublicWebchatWidget.widget_key == widget_key.strip()))
    if widget is None or not widget.is_active:
        raise HTTPException(status_code=404, detail="Webchat widget not found or inactive")
    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == widget.auth_tenant_id))
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
    return widget, tenant


def _assert_origin_allowed(widget: PublicWebchatWidget, origin: str | None) -> str:
    if not origin:
        raise HTTPException(status_code=403, detail="Origin header is required for webchat")
    try:
        norm = normalize_webchat_origin(origin)
    except HTTPException as exc:
        raise HTTPException(status_code=403, detail=str(exc.detail)) from exc
    if norm not in (widget.allowed_origins or []):
        raise HTTPException(status_code=403, detail="Origin is not authorized for this webchat widget")
    return norm


def create_webchat_session(
    db: Session,
    *,
    widget_key: str,
    origin: str | None,
    visitor_name: str | None = None,
    visitor_email: str | None = None,
    client_ip: str = "unknown",
    limiter: IngestRateLimiter | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    widget, tenant = _resolve_active_widget_and_tenant(db, widget_key)
    norm_origin = _assert_origin_allowed(widget, origin)
    rl = limiter or _get_limiter()
    if not rl.allow(f"wc_init:{widget.widget_key}:{client_ip}", widget.rate_limit_per_minute):
        raise HTTPException(status_code=429, detail="Webchat rate limit exceeded")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_webchat_ready(db, tenant)

    raw_token = f"wct_{secrets.token_urlsafe(32)}"
    session_uid = f"webchat:{uuid4().hex}"
    clean_name = (visitor_name or "").strip()[:160] or "Visitante Web"
    clean_email = normalize_email(visitor_email) if visitor_email else None

    cliente = Cliente(
        rut=f"wc:{uuid4().hex[:16]}",
        nombre=clean_name,
        email=clean_email,
        whatsapp_id=session_uid,
        canal_origen="webchat",
        consentimiento_datos=True,
        fecha_consentimiento=current,
    )
    db.add(cliente)
    db.flush()
    lead, lead_created = get_or_create_initial_lead(db, cliente.id)
    if lead_created:
        publish_domain_event_in_tx(
            db,
            tenant,
            event_type="lead.created",
            aggregate_type="lead",
            aggregate_id=lead.id,
            payload={"lead_id": lead.id, "contact_id": cliente.id, "channel": "webchat"},
            occurred_at=current,
        )

    conversation = Conversation(
        session_id=session_uid,
        message={"channel": "webchat", "widget_key": widget.widget_key, "origin": norm_origin},
    )
    db.add(conversation)
    db.flush()

    expires_at = current + timedelta(minutes=widget.session_ttl_minutes)
    wc_session = WebchatSession(
        widget_key=widget.widget_key,
        token_hash=_token_hash(raw_token),
        visitor_name=clean_name,
        visitor_email=clean_email,
        origin=norm_origin,
        client_id=cliente.id,
        conversation_id=conversation.id,
        status="active",
        expires_at=expires_at,
        created_at=current,
        last_seen_at=current,
    )
    db.add(wc_session)
    db.flush()

    welcome_msg = Message(
        whatsapp_id=session_uid,
        rol="agente",
        mensaje=widget.welcome_message,
        creado_en=current,
        connection_id="default",
        channel="webchat",
        external_message_id=f"wc-welcome:{wc_session.id}",
        direction="outbound",
        message_type="text",
        delivery_status="delivered",
    )
    db.add(welcome_msg)
    db.flush()
    db.commit()

    return {
        "session_token": raw_token,
        "conversation_id": conversation.id,
        "welcome_message": widget.welcome_message,
        "cursor": welcome_msg.id,
        "expires_at": expires_at,
    }


def _load_valid_session(
    db: Session,
    tenant: TenantContext,
    widget: PublicWebchatWidget,
    session_token: str | None,
    origin: str | None,
    *,
    now: datetime,
) -> tuple[WebchatSession, Conversation]:
    norm_origin = _assert_origin_allowed(widget, origin)
    if not session_token or not session_token.strip():
        raise HTTPException(status_code=401, detail="Webchat session token is required")
    bind_tenant_session(db, tenant.schema_name)
    _require_webchat_ready(db, tenant)

    session = db.scalar(
        select(WebchatSession).where(
            WebchatSession.token_hash == _token_hash(session_token.strip()),
            WebchatSession.widget_key == widget.widget_key,
        )
    )
    if session is None or session.status != "active" or session.expires_at <= now:
        raise HTTPException(status_code=401, detail="Webchat session is invalid or expired")
    if session.origin != norm_origin:
        raise HTTPException(status_code=403, detail="Webchat session origin mismatch")
    conv = db.get(Conversation, session.conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    session.last_seen_at = now
    return session, conv


def _default_reply(
    widget: PublicWebchatWidget,
    tenant: TenantContext,
    session: WebchatSession,
    body: str,
) -> str:
    agent_url = get_settings().agent_core_url.strip()
    internal_token = get_settings().internal_token.strip()
    if agent_url and internal_token:
        req = urllib.request.Request(
            f"{agent_url.rstrip('/')}/api/v1/agent/messages",
            method="POST",
            data=json.dumps(
                {
                    "tenant_id": str(tenant.auth_tenant_id),
                    "channel": "webchat",
                    "conversation_id": str(session.conversation_id),
                    "agent_id": widget.agent_id,
                    "customer": {"external_id": str(session.client_id), "name": session.visitor_name or "Visitante Web"},
                    "message": {"type": "text", "content": body, "attachments": []},
                    "metadata": {"raw_payload": {"operational_conversation_id": session.conversation_id}},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Internal-Token": internal_token},
        )
        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
                data = parsed.get("data") if isinstance(parsed, dict) else parsed
                if isinstance(data, dict) and isinstance(data.get("reply"), dict):
                    content = data["reply"].get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            pass
    return "Recibimos tu mensaje. Un integrante del equipo te responderá en breve por este medio."


def post_webchat_message(
    db: Session,
    *,
    widget_key: str,
    session_token: str | None,
    origin: str | None,
    body: str,
    idempotency_key: str,
    reply_provider: Callable[[PublicWebchatWidget, TenantContext, WebchatSession, str], str] | None = None,
    limiter: IngestRateLimiter | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    clean_body = body.strip()
    clean_idem = idempotency_key.strip()[:120]
    if not clean_body:
        raise HTTPException(status_code=422, detail="Message body cannot be empty")
    if not clean_idem:
        raise HTTPException(status_code=422, detail="idempotency_key cannot be empty")

    current = _now(now)
    widget, tenant = _resolve_active_widget_and_tenant(db, widget_key)
    session, conv = _load_valid_session(db, tenant, widget, session_token, origin, now=current)

    rl = limiter or _get_limiter()
    if not rl.allow(f"wc_msg:{widget.widget_key}:{session.id}", widget.rate_limit_per_minute):
        raise HTTPException(status_code=429, detail="Webchat message rate limit exceeded")

    ext_id = f"wc:{session.id}:{clean_idem}"
    existing = db.scalar(
        select(Message).where(
            Message.connection_id == "default",
            Message.channel == "webchat",
            Message.external_message_id == ext_id,
        )
    )
    ctrl_info = get_conversation_control(db, tenant, conv.id)
    control_mode = ctrl_info["mode"]
    if existing is not None:
        reply_row = db.scalar(
            select(Message).where(
                Message.connection_id == "default",
                Message.channel == "webchat",
                Message.external_message_id == f"wc-ai:{session.id}:{clean_idem}",
            )
        )
        db.commit()
        return {
            "conversation_id": conv.id,
            "inbound_message": _msg_to_dict(existing),
            "reply_message": _msg_to_dict(reply_row) if reply_row else None,
            "ai_paused": control_mode != "ai_active",
            "control_mode": control_mode,
            "cursor": (reply_row or existing).id,
            "duplicate": True,
        }

    inbound_msg = Message(
        whatsapp_id=conv.session_id,
        rol="usuario",
        mensaje=clean_body,
        creado_en=current,
        connection_id="default",
        channel="webchat",
        external_message_id=ext_id,
        direction="inbound",
        message_type="text",
        delivery_status="received",
    )
    db.add(inbound_msg)
    db.flush()

    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="message.inbound.received",
        aggregate_type="conversation",
        aggregate_id=conv.id,
        payload={
            "conversation_id": conv.id,
            "contact_id": session.client_id,
            "channel": "webchat",
            "widget_key": widget.widget_key,
            "message_id": ext_id,
        },
        occurred_at=current,
    )
    cancel_waiting_runs_in_tx(
        db,
        tenant,
        event_type="message.inbound.received",
        contact_id=session.client_id,
        conversation_id=conv.id,
        reason="customer_replied",
        now=current,
    )

    ai_ok, _ = is_ai_permitted_for_conversation_in_tx(db, tenant, conv.id)
    reply_msg: Message | None = None
    if ai_ok:
        generator = reply_provider or _default_reply
        reply_text = generator(widget, tenant, session, clean_body).strip()
        if reply_text:
            reply_msg = Message(
                whatsapp_id=conv.session_id,
                rol="agente",
                mensaje=reply_text,
                creado_en=current,
                connection_id="default",
                channel="webchat",
                external_message_id=f"wc-ai:{session.id}:{clean_idem}",
                direction="outbound",
                message_type="text",
                delivery_status="delivered",
            )
            db.add(reply_msg)
            db.flush()

    db.commit()
    return {
        "conversation_id": conv.id,
        "inbound_message": _msg_to_dict(inbound_msg),
        "reply_message": _msg_to_dict(reply_msg) if reply_msg else None,
        "ai_paused": not ai_ok,
        "control_mode": control_mode,
        "cursor": (reply_msg or inbound_msg).id,
        "duplicate": False,
    }


def list_webchat_messages(
    db: Session,
    *,
    widget_key: str,
    session_token: str | None,
    origin: str | None,
    after_id: int = 0,
    limit: int = 50,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    widget, tenant = _resolve_active_widget_and_tenant(db, widget_key)
    _, conv = _load_valid_session(db, tenant, widget, session_token, origin, now=current)

    capped = max(1, min(limit, 100))
    rows = list(
        db.scalars(
            select(Message)
            .where(Message.whatsapp_id == conv.session_id, Message.id > max(0, after_id))
            .order_by(Message.id.asc())
            .limit(capped + 1)
        ).all()
    )
    has_more = len(rows) > capped
    page = rows[:capped]
    next_cursor = page[-1].id if page else max(0, after_id)
    ctrl_info = get_conversation_control(db, tenant, conv.id)
    db.commit()
    return {
        "conversation_id": conv.id,
        "items": [_msg_to_dict(row) for row in page],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "control_mode": ctrl_info["mode"],
    }
