"""Durable ActionOutbox worker dispatcher for campaigns, emails, HITL replies, webhooks, and notifications."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import logging
import re
import socket
from typing import Protocol
import urllib.error
import urllib.request
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.tenant_resolver import TenantContext
from app.public_models.tenant_runtime import TenantRuntime
from app.services.action_outbox_service import (
    begin_outbox_execution,
    cancel_outbox_action,
    claim_next_outbox_jobs,
    complete_outbox_action,
    fail_outbox_action,
    outbox_ready,
    reconcile_unknown_outbox_action,
)
from app.services.ai_extensions_service import record_notification_receipt
from app.services.campaign_service import (
    issue_unsubscribe_token,
    promote_due_scheduled_campaigns,
    render_template_preview,
)
from app.services.consent_authorization_service import authorize_outbox_delivery
from app.services.post_v1_service import _validate_webhook_url, record_webhook_attempt
from app.services.tenant_data import bind_tenant_session
from app.services.workflow_service import process_tenant_workflows
from app.tenant_models.action_outbox import ActionOutboxJob
from app.tenant_models.ai_extensions import ExternalNotificationDelivery
from app.tenant_models.campaigns import (
    Campaign,
    CampaignRecipient,
    DeliveryAttempt,
    TemplateVersion,
    TenantChannelConnection,
)
from app.tenant_models.operations import Cliente, Message
from app.tenant_models.post_v1 import WebhookDelivery, WebhookSubscription


logger = logging.getLogger("operational-worker")

SUPPORTED_ACTION_TYPES: tuple[str, ...] = (
    "campaign.delivery.send",
    "conversation.email.send",
    "conversation.human_reply.send",
    "webhook.deliver",
    "notification.external.send",
)
_SAFE_MAIL_IDEM_RE = re.compile(r"^[A-Za-z0-9._:-]{8,200}$")


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Dispatcher timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _safe_mail_idempotency_key(job_id: int, raw_key: str) -> str:
    if _SAFE_MAIL_IDEM_RE.fullmatch(raw_key):
        return raw_key
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:32]
    return f"outbox:{job_id}:{digest}"


def _is_definitive_4xx(status_code: int | None) -> bool:
    return status_code is not None and 400 <= status_code < 500 and status_code not in (408, 409, 429)


@dataclass(frozen=True)
class TransportResult:
    status_code: int | None
    body: dict | None = None
    error: str | None = None
    definitely_not_sent: bool = False


class OutboxTransport(Protocol):
    def send_email(
        self,
        *,
        sender_key: str,
        to: list[str],
        subject: str,
        text: str,
        html: str | None,
        idempotency_key: str,
        reply_to: str | None = None,
    ) -> TransportResult:
        ...

    def send_whatsapp_human_reply(
        self,
        *,
        auth_tenant_id: int,
        phone: str,
        text: str,
        idempotency_key: str,
    ) -> TransportResult:
        ...

    def deliver_webhook(
        self,
        *,
        target_url: str,
        event_id: str,
        event_type: str,
        signature: str,
        payload: dict,
    ) -> TransportResult:
        ...


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_webhook_target_with_dns(url: str) -> str:
    """Validate HTTPS webhook URL and verify DNS does not resolve to private/loopback/reserved IPs."""
    clean = _validate_webhook_url(url)
    parsed = urlparse(clean)
    hostname = parsed.hostname
    port = parsed.port or 443
    try:
        addr_infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"Webhook DNS resolution failed: {exc}") from exc
    if not addr_infos:
        raise HTTPException(status_code=422, detail="Webhook DNS resolution returned no addresses")
    for info in addr_infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Webhook resolved to invalid IP") from exc
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise HTTPException(status_code=422, detail="Webhook target_url resolves to disallowed IP")
    return clean


class StdlibOutboxTransport:
    """Synchronous stdlib HTTP transport for mail-service, Baileys, and signed webhooks."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._no_redirect_opener = urllib.request.build_opener(_NoRedirectHandler())

    def can_send_email(self) -> bool:
        return bool(self.settings.mail_gateway_url.strip() and self.settings.mail_internal_api_key.strip())

    def can_send_whatsapp(self) -> bool:
        return bool(self.settings.baileys_service_url.strip() and self.settings.baileys_internal_token.strip())

    def _post_json(
        self,
        url: str,
        payload: dict,
        headers: dict[str, str],
        *,
        allow_redirects: bool = False,
    ) -> TransportResult:
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        opener = urllib.request.build_opener() if allow_redirects else self._no_redirect_opener
        try:
            with opener.open(req, timeout=self.settings.worker_http_timeout_seconds) as resp:
                raw = resp.read().decode("utf-8", errors="replace").strip()
                parsed = json.loads(raw) if raw else None
                if not isinstance(parsed, dict):
                    parsed = None
                return TransportResult(status_code=int(resp.status), body=parsed)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace").strip() if exc.fp else ""
            parsed = None
            if raw:
                try:
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        parsed = loaded
                except json.JSONDecodeError:
                    parsed = None
            return TransportResult(
                status_code=int(exc.code),
                body=parsed,
                error=f"http_{exc.code}",
                definitely_not_sent=(300 <= int(exc.code) < 400),
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return TransportResult(status_code=None, error=str(exc)[:120] or "network_error", definitely_not_sent=False)

    def send_email(
        self,
        *,
        sender_key: str,
        to: list[str],
        subject: str,
        text: str,
        html: str | None,
        idempotency_key: str,
        reply_to: str | None = None,
    ) -> TransportResult:
        if not self.can_send_email():
            return TransportResult(None, error="mail_gateway_unconfigured", definitely_not_sent=True)
        url = f"{self.settings.mail_gateway_url.rstrip('/')}/api/v1/emails/send"
        body: dict = {
            "sender_key": sender_key,
            "to": to,
            "subject": subject.replace("\r", " ").replace("\n", " ")[:240],
            "text": text,
            "idempotency_key": idempotency_key,
        }
        if html:
            body["html"] = html
        if reply_to:
            body["reply_to"] = reply_to
        return self._post_json(
            url,
            body,
            {"Authorization": f"Bearer {self.settings.mail_internal_api_key.strip()}"},
            allow_redirects=False,
        )

    def send_whatsapp_human_reply(
        self,
        *,
        auth_tenant_id: int,
        phone: str,
        text: str,
        idempotency_key: str,
    ) -> TransportResult:
        if not self.can_send_whatsapp():
            return TransportResult(None, error="baileys_unconfigured", definitely_not_sent=True)
        url = f"{self.settings.baileys_service_url.rstrip('/')}/internal/baileys/tenants/{auth_tenant_id}/messages"
        res = self._post_json(
            url,
            {"phone": phone, "text": text, "idempotency_key": idempotency_key},
            {"Authorization": f"Bearer {self.settings.baileys_internal_token.strip()}"},
            allow_redirects=False,
        )
        if res.status_code == 409 and isinstance(res.body, dict) and res.body.get("sent") is False:
            return TransportResult(
                status_code=409,
                body=res.body,
                error=str(res.body.get("error") or "http_409"),
                definitely_not_sent=True,
            )
        return res

    def deliver_webhook(
        self,
        *,
        target_url: str,
        event_id: str,
        event_type: str,
        signature: str,
        payload: dict,
    ) -> TransportResult:
        try:
            validated_url = validate_webhook_target_with_dns(target_url)
        except HTTPException as exc:
            return TransportResult(None, error=str(exc.detail)[:120] or "ssrf_blocked", definitely_not_sent=True)
        return self._post_json(
            validated_url,
            {"event_id": event_id, "event_type": event_type, "payload": payload},
            {
                "X-KronFlow-Signature": signature,
                "X-KronFlow-Event-Id": event_id,
                "X-KronFlow-Event-Type": event_type,
            },
            allow_redirects=False,
        )


def _transport_ready(transport: OutboxTransport, method_name: str) -> bool:
    checker = getattr(transport, method_name, None)
    if callable(checker):
        return bool(checker())
    return True


def _record_campaign_recipient_outcome(
    db: Session,
    tenant: TenantContext,
    *,
    recipient_id: int | None,
    job: ActionOutboxJob,
    provider: str,
    status_value: str,
    attempt_outcome: str | None,
    provider_message_id: str | None = None,
    error_code: str | None = None,
    now: datetime,
) -> None:
    if recipient_id is None:
        return
    bind_tenant_session(db, tenant.schema_name)
    rec = db.get(CampaignRecipient, recipient_id)
    if rec is None:
        return
    rec.status = status_value
    if provider_message_id is not None:
        rec.provider_message_id = provider_message_id
    rec.last_error = error_code[:120] if error_code else None
    rec.updated_at = now
    if attempt_outcome is not None:
        db.add(
            DeliveryAttempt(
                campaign_recipient_id=rec.id,
                attempt_number=job.attempts,
                idempotency_key=job.idempotency_key,
                provider=provider[:32],
                provider_message_id=provider_message_id,
                outcome=attempt_outcome,
                error_code=error_code[:64] if error_code else None,
                created_at=now,
            )
        )
    db.commit()


def _dispatch_campaign_delivery(
    db: Session,
    tenant: TenantContext,
    job: ActionOutboxJob,
    *,
    settings: Settings,
    transport: OutboxTransport,
    now: datetime,
) -> str:
    payload = job.payload or {}
    campaign_id = payload["campaign_id"]
    contact_point_id = payload["contact_point_id"]
    client_id = payload["client_id"]
    channel = payload["channel"]
    destination = payload["destination"]
    purpose = payload["purpose"]

    bind_tenant_session(db, tenant.schema_name)
    campaign = db.get(Campaign, campaign_id)
    recipient = db.scalar(
        select(CampaignRecipient).where(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.contact_point_id == contact_point_id,
        )
    )
    recipient_id = recipient.id if recipient is not None else None
    conn = db.get(TenantChannelConnection, campaign.connection_id) if campaign else None

    if campaign is None or campaign.status == "cancelled":
        cancel_outbox_action(db, tenant, job.id, reason="campaign_cancelled", now=now)
        _record_campaign_recipient_outcome(
            db, tenant, recipient_id=recipient_id, job=job, provider=(conn.provider if conn else "unknown"),
            status_value="suppressed", attempt_outcome=None, error_code="campaign_cancelled", now=now,
        )
        return "suppressed"

    if campaign.status != "running":
        fail_outbox_action(
            db, tenant, job.id, job.claim_token,
            error=f"campaign_{campaign.status}", retryable=True, retry_delay_seconds=60, now=now,
        )
        return "skipped"

    if conn is None or conn.status != "active" or not conn.verified:
        cancel_outbox_action(db, tenant, job.id, reason="connection_unavailable", now=now)
        _record_campaign_recipient_outcome(
            db, tenant, recipient_id=recipient_id, job=job, provider=(conn.provider if conn else "unknown"),
            status_value="suppressed", attempt_outcome=None, error_code="connection_unavailable", now=now,
        )
        return "suppressed"

    if conn.provider == "stub" and not settings.worker_allow_stub_dispatch:
        fail_outbox_action(
            db, tenant, job.id, job.claim_token, error="stub_dispatch_disabled", retryable=False, now=now,
        )
        _record_campaign_recipient_outcome(
            db, tenant, recipient_id=recipient_id, job=job, provider=conn.provider,
            status_value="failed", attempt_outcome="failed", error_code="stub_dispatch_disabled", now=now,
        )
        return "failed"

    if conn.provider == "resend" and not _transport_ready(transport, "can_send_email"):
        fail_outbox_action(
            db, tenant, job.id, job.claim_token,
            error="mail_gateway_unconfigured", retryable=True, retry_delay_seconds=60, now=now,
        )
        return "skipped"

    auth = authorize_outbox_delivery(
        db, tenant, job_id=job.id, claim_token=job.claim_token,
        client_id=client_id, channel=channel, destination=destination,
        purpose=purpose, point_active=True, point_verified=True, now=now,
    )
    if not auth.authorized:
        _record_campaign_recipient_outcome(
            db, tenant, recipient_id=recipient_id, job=job, provider=conn.provider,
            status_value="suppressed", attempt_outcome=None, error_code=auth.reason, now=now,
        )
        return "suppressed"

    bind_tenant_session(db, tenant.schema_name)
    tv = db.get(TemplateVersion, campaign.template_version_id)
    client = db.get(Cliente, client_id)
    if tv is None:
        fail_outbox_action(db, tenant, job.id, job.claim_token, error="template_missing", retryable=False, now=now)
        _record_campaign_recipient_outcome(
            db, tenant, recipient_id=recipient_id, job=job, provider=conn.provider,
            status_value="failed", attempt_outcome="failed", error_code="template_missing", now=now,
        )
        return "failed"

    variables: dict[str, str] = {}
    if client is not None:
        if client.nombre:
            variables["name"] = client.nombre
        if client.email:
            variables["email"] = client.email
    declared = set(tv.declared_variables or [])
    if "unsubscribe_url" in declared and settings.public_api_base_url.strip():
        issued = issue_unsubscribe_token(
            db, tenant, channel=channel, destination=destination, purpose=purpose, client_id=client_id, now=now,
        )
        variables["unsubscribe_url"] = (
            f"{settings.public_api_base_url.rstrip('/')}/api/v1/public/channels/unsubscribe/{issued['token']}"
        )

    rendered = render_template_preview(tv, variables)

    if conn.provider == "stub":
        provider_msg_id = f"stub:{conn.provider}:c{campaign_id}:j{job.id}"
        complete_outbox_action(
            db, tenant, job.id, job.claim_token,
            effect_reference=provider_msg_id,
            effect_payload={"provider": "stub", "stub": True, "destination": destination, "status": "accepted"},
            now=now,
        )
        _record_campaign_recipient_outcome(
            db, tenant, recipient_id=recipient_id, job=job, provider=conn.provider,
            status_value="accepted", attempt_outcome="accepted", provider_message_id=provider_msg_id, now=now,
        )
        return "completed"

    res = transport.send_email(
        sender_key=settings.mail_sender_key,
        to=[destination],
        subject=rendered["subject"] or campaign.name,
        text=rendered["body_text"],
        html=rendered["body_html"],
        idempotency_key=_safe_mail_idempotency_key(job.id, job.idempotency_key),
        reply_to=conn.sender_address,
    )
    if res.status_code is not None and 200 <= res.status_code < 300:
        provider_msg_id = str((res.body or {}).get("message_id") or f"resend:c{campaign_id}:j{job.id}")
        complete_outbox_action(
            db, tenant, job.id, job.claim_token,
            effect_reference=provider_msg_id,
            effect_payload={"provider": "resend", "destination": destination, "status": "accepted"},
            now=now,
        )
        _record_campaign_recipient_outcome(
            db, tenant, recipient_id=recipient_id, job=job, provider=conn.provider,
            status_value="accepted", attempt_outcome="accepted", provider_message_id=provider_msg_id, now=now,
        )
        return "completed"

    if _is_definitive_4xx(res.status_code) or res.definitely_not_sent:
        err = res.error or f"http_{res.status_code}"
        fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=False, now=now)
        _record_campaign_recipient_outcome(
            db, tenant, recipient_id=recipient_id, job=job, provider=conn.provider,
            status_value="failed", attempt_outcome="failed", error_code=err, now=now,
        )
        return "failed"

    err = res.error or (f"http_{res.status_code}" if res.status_code else "mail_timeout")
    fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=True, now=now)
    _record_campaign_recipient_outcome(
        db, tenant, recipient_id=recipient_id, job=job, provider=conn.provider,
        status_value="unknown", attempt_outcome="unknown", error_code=err, now=now,
    )
    return "unknown"


def _dispatch_conversation_email(
    db: Session,
    tenant: TenantContext,
    job: ActionOutboxJob,
    *,
    settings: Settings,
    transport: OutboxTransport,
    now: datetime,
) -> str:
    payload = job.payload or {}
    connection_id = payload["connection_id"]
    to_email = payload["to"]
    subject = payload["subject"]
    body_text = payload["body_text"]

    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == tenant.auth_tenant_id))
    bind_tenant_session(db, tenant.schema_name)
    conn = db.get(TenantChannelConnection, connection_id)
    msg = db.scalar(
        select(Message).where(
            Message.connection_id == f"email:{connection_id}",
            Message.channel == "email",
            Message.external_message_id == job.idempotency_key,
        )
    )

    if (runtime is not None and runtime.status != "active") or conn is None or conn.status != "active" or not conn.verified:
        reason = "tenant_suspended" if (runtime and runtime.status != "active") else "connection_unavailable"
        cancel_outbox_action(db, tenant, job.id, reason=reason, now=now)
        if msg is not None:
            bind_tenant_session(db, tenant.schema_name)
            m = db.get(Message, msg.id)
            if m is not None:
                m.delivery_status = "failed"
                db.commit()
        return "suppressed"

    if conn.provider == "stub" and not settings.worker_allow_stub_dispatch:
        fail_outbox_action(db, tenant, job.id, job.claim_token, error="stub_dispatch_disabled", retryable=False, now=now)
        return "failed"

    if conn.provider == "resend" and not _transport_ready(transport, "can_send_email"):
        fail_outbox_action(
            db, tenant, job.id, job.claim_token,
            error="mail_gateway_unconfigured", retryable=True, retry_delay_seconds=60, now=now,
        )
        return "skipped"

    begin_outbox_execution(db, tenant, job.id, job.claim_token, now=now)

    if conn.provider == "stub":
        provider_msg_id = f"stub:email:j{job.id}"
        complete_outbox_action(
            db, tenant, job.id, job.claim_token,
            effect_reference=provider_msg_id,
            effect_payload={"provider": "stub", "stub": True, "to": to_email},
            now=now,
        )
        if msg is not None:
            bind_tenant_session(db, tenant.schema_name)
            m = db.get(Message, msg.id)
            if m is not None:
                m.provider_message_id = provider_msg_id
                m.delivery_status = "sent"
                db.commit()
        return "completed"

    res = transport.send_email(
        sender_key=settings.mail_sender_key,
        to=[to_email],
        subject=subject,
        text=body_text,
        html=None,
        idempotency_key=_safe_mail_idempotency_key(job.id, job.idempotency_key),
        reply_to=conn.sender_address,
    )
    if res.status_code is not None and 200 <= res.status_code < 300:
        provider_msg_id = str((res.body or {}).get("message_id") or f"resend:email:j{job.id}")
        complete_outbox_action(
            db, tenant, job.id, job.claim_token,
            effect_reference=provider_msg_id,
            effect_payload={"provider": "resend", "to": to_email},
            now=now,
        )
        if msg is not None:
            bind_tenant_session(db, tenant.schema_name)
            m = db.get(Message, msg.id)
            if m is not None:
                m.provider_message_id = provider_msg_id
                m.delivery_status = "sent"
                db.commit()
        return "completed"

    err = res.error or (f"http_{res.status_code}" if res.status_code else "mail_timeout")
    if _is_definitive_4xx(res.status_code) or res.definitely_not_sent:
        fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=False, now=now)
        if msg is not None:
            bind_tenant_session(db, tenant.schema_name)
            m = db.get(Message, msg.id)
            if m is not None:
                m.delivery_status = "failed"
                db.commit()
        return "failed"

    fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=True, now=now)
    return "unknown"


def _dispatch_human_reply(
    db: Session,
    tenant: TenantContext,
    job: ActionOutboxJob,
    *,
    transport: OutboxTransport,
    now: datetime,
) -> str:
    payload = job.payload or {}
    conversation_id = payload["conversation_id"]
    session_id = str(payload["session_id"])
    channel = payload.get("channel") or "whatsapp"
    body = payload["body"]

    raw_key = job.idempotency_key.removeprefix(f"conv:{conversation_id}:")
    external_id = f"human:{conversation_id}:{raw_key}"

    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == tenant.auth_tenant_id))
    bind_tenant_session(db, tenant.schema_name)
    msg = db.scalar(
        select(Message).where(
            Message.connection_id == "default",
            Message.channel == channel,
            Message.external_message_id == external_id,
        )
    )

    if runtime is not None and runtime.status != "active":
        cancel_outbox_action(db, tenant, job.id, reason="tenant_suspended", now=now)
        return "suppressed"

    if channel == "webchat":
        begin_outbox_execution(db, tenant, job.id, job.claim_token, now=now)
        ref = f"webchat:msg:{msg.id if msg is not None else job.id}"
        complete_outbox_action(
            db, tenant, job.id, job.claim_token,
            effect_reference=ref,
            effect_payload={"channel": "webchat", "status": "delivered"},
            now=now,
        )
        if msg is not None:
            bind_tenant_session(db, tenant.schema_name)
            m = db.get(Message, msg.id)
            if m is not None:
                m.delivery_status = "delivered"
                db.commit()
        return "completed"

    if channel == "whatsapp":
        consent_ok = db.scalar(select(Cliente.consentimiento_datos).where(Cliente.whatsapp_id == session_id))
        if consent_ok is not True:
            cancel_outbox_action(db, tenant, job.id, reason="consent_withdrawn", now=now)
            if msg is not None:
                bind_tenant_session(db, tenant.schema_name)
                m = db.get(Message, msg.id)
                if m is not None:
                    m.delivery_status = "failed"
                    db.commit()
            return "suppressed"
    else:
        fail_outbox_action(db, tenant, job.id, job.claim_token, error=f"unsupported_channel:{channel}", retryable=False, now=now)
        return "failed"

    if not _transport_ready(transport, "can_send_whatsapp"):
        fail_outbox_action(
            db, tenant, job.id, job.claim_token,
            error="baileys_unconfigured", retryable=True, retry_delay_seconds=60, now=now,
        )
        return "skipped"

    begin_outbox_execution(db, tenant, job.id, job.claim_token, now=now)
    res = transport.send_whatsapp_human_reply(
        auth_tenant_id=tenant.auth_tenant_id,
        phone=session_id,
        text=body,
        idempotency_key=job.idempotency_key,
    )
    if res.status_code is not None and 200 <= res.status_code < 300:
        provider_msg_id = (res.body or {}).get("provider_message_id")
        complete_outbox_action(
            db, tenant, job.id, job.claim_token,
            effect_reference=str(provider_msg_id) if provider_msg_id else None,
            effect_payload={"channel": channel, "status": "sent"},
            now=now,
        )
        if msg is not None:
            bind_tenant_session(db, tenant.schema_name)
            m = db.get(Message, msg.id)
            if m is not None:
                if provider_msg_id:
                    m.provider_message_id = str(provider_msg_id)
                m.delivery_status = "sent"
                db.commit()
        return "completed"

    err = res.error or (f"http_{res.status_code}" if res.status_code else "whatsapp_timeout")
    if res.definitely_not_sent:
        is_retryable = bool(isinstance(res.body, dict) and res.body.get("retryable") is True)
        if is_retryable:
            fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=True, now=now)
            reconcile_unknown_outbox_action(
                db, tenant, job.id, verified_applied=False, retry_delay_seconds=30, now=now,
            )
            return "retried"
        fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=False, now=now)
        if msg is not None:
            bind_tenant_session(db, tenant.schema_name)
            m = db.get(Message, msg.id)
            if m is not None:
                m.delivery_status = "failed"
                db.commit()
        return "failed"

    if _is_definitive_4xx(res.status_code):
        fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=False, now=now)
        if msg is not None:
            bind_tenant_session(db, tenant.schema_name)
            m = db.get(Message, msg.id)
            if m is not None:
                m.delivery_status = "failed"
                db.commit()
        return "failed"

    fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=True, now=now)
    return "unknown"


def _dispatch_webhook_delivery(
    db: Session,
    tenant: TenantContext,
    job: ActionOutboxJob,
    *,
    transport: OutboxTransport,
    now: datetime,
) -> str:
    bind_tenant_session(db, tenant.schema_name)
    delivery = db.scalar(select(WebhookDelivery).where(WebhookDelivery.outbox_job_id == job.id))
    if delivery is None:
        fail_outbox_action(db, tenant, job.id, job.claim_token, error="webhook_delivery_missing", retryable=False, now=now)
        return "failed"
    sub = db.get(WebhookSubscription, delivery.subscription_id)
    if sub is None or not sub.is_active:
        cancel_outbox_action(db, tenant, job.id, reason="subscription_inactive", now=now)
        return "suppressed"

    try:
        validate_webhook_target_with_dns(sub.target_url)
    except HTTPException as exc:
        err = str(exc.detail)[:120] or "ssrf_blocked"
        fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=False, now=now)
        record_webhook_attempt(db, tenant, delivery.id, http_status=None, error=err, now=now)
        return "failed"

    begin_outbox_execution(db, tenant, job.id, job.claim_token, now=now)
    res = transport.deliver_webhook(
        target_url=sub.target_url,
        event_id=delivery.event_id,
        event_type=delivery.event_type,
        signature=delivery.signature,
        payload=delivery.payload,
    )
    updated_delivery = record_webhook_attempt(
        db, tenant, delivery.id, http_status=res.status_code, error=res.error, now=now,
    )

    if res.status_code is not None and 200 <= res.status_code < 300:
        complete_outbox_action(
            db, tenant, job.id, job.claim_token,
            effect_reference=f"http:{res.status_code}",
            effect_payload={"http_status": res.status_code, "delivery_id": delivery.id},
            now=now,
        )
        return "completed"

    err = res.error or (f"http_{res.status_code}" if res.status_code else "webhook_timeout")
    if updated_delivery["status"] == "dead_letter" or _is_definitive_4xx(res.status_code) or res.definitely_not_sent:
        fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=False, now=now)
        return "failed"

    if res.status_code is not None and res.status_code in (408, 429, 500, 502, 503, 504):
        fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=True, now=now)
        backoff = min(300, 30 * (2 ** max(0, job.attempts - 1)))
        reconcile_unknown_outbox_action(
            db, tenant, job.id, verified_applied=False, retry_delay_seconds=backoff, now=now,
        )
        return "retried"

    fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=True, now=now)
    return "unknown"


def _dispatch_external_notification(
    db: Session,
    tenant: TenantContext,
    job: ActionOutboxJob,
    *,
    settings: Settings,
    transport: OutboxTransport,
    now: datetime,
) -> str:
    bind_tenant_session(db, tenant.schema_name)
    delivery = db.scalar(
        select(ExternalNotificationDelivery).where(ExternalNotificationDelivery.outbox_job_id == job.id)
    )
    if delivery is None:
        fail_outbox_action(db, tenant, job.id, job.claim_token, error="notification_missing", retryable=False, now=now)
        return "failed"

    if delivery.channel == "webhook_stub":
        if not settings.worker_allow_stub_dispatch:
            fail_outbox_action(db, tenant, job.id, job.claim_token, error="stub_dispatch_disabled", retryable=False, now=now)
            record_notification_receipt(db, tenant, delivery.id, status_value="failed", now=now)
            return "failed"
        begin_outbox_execution(db, tenant, job.id, job.claim_token, now=now)
        ref = f"stub:notif:{delivery.id}"
        complete_outbox_action(
            db, tenant, job.id, job.claim_token,
            effect_reference=ref, effect_payload={"stub": True, "channel": "webhook_stub"}, now=now,
        )
        record_notification_receipt(db, tenant, delivery.id, status_value="delivered", receipt_ref=ref, now=now)
        return "completed"

    if delivery.channel != "email":
        fail_outbox_action(db, tenant, job.id, job.claim_token, error="unsupported_channel", retryable=False, now=now)
        record_notification_receipt(db, tenant, delivery.id, status_value="failed", now=now)
        return "failed"

    if not _transport_ready(transport, "can_send_email"):
        fail_outbox_action(
            db, tenant, job.id, job.claim_token,
            error="mail_gateway_unconfigured", retryable=True, retry_delay_seconds=60, now=now,
        )
        return "skipped"

    begin_outbox_execution(db, tenant, job.id, job.claim_token, now=now)
    subject = f"[KronFlow] {delivery.event_type}"
    text = json.dumps(delivery.payload or {}, ensure_ascii=False)
    res = transport.send_email(
        sender_key=settings.mail_sender_key,
        to=[delivery.recipient],
        subject=subject,
        text=text,
        html=None,
        idempotency_key=_safe_mail_idempotency_key(job.id, job.idempotency_key),
    )
    if res.status_code is not None and 200 <= res.status_code < 300:
        ref = str((res.body or {}).get("message_id") or f"notif:{delivery.id}")
        complete_outbox_action(
            db, tenant, job.id, job.claim_token,
            effect_reference=ref, effect_payload={"channel": "email", "recipient": delivery.recipient}, now=now,
        )
        record_notification_receipt(db, tenant, delivery.id, status_value="delivered", receipt_ref=ref, now=now)
        return "completed"

    err = res.error or (f"http_{res.status_code}" if res.status_code else "mail_timeout")
    if _is_definitive_4xx(res.status_code) or res.definitely_not_sent:
        fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=False, now=now)
        record_notification_receipt(db, tenant, delivery.id, status_value="failed", now=now)
        return "failed"

    fail_outbox_action(db, tenant, job.id, job.claim_token, error=err, retryable=True, now=now)
    return "unknown"


def dispatch_tenant_outbox_batch(
    db: Session,
    tenant: TenantContext,
    *,
    settings: Settings,
    transport: OutboxTransport,
    limit: int = 20,
    lease_seconds: int = 120,
    now: datetime | None = None,
) -> dict:
    """Promote scheduled campaigns and process one batch of outbox jobs for a tenant."""
    current = _utc_now(now)
    promoted = promote_due_scheduled_campaigns(db, tenant, now=current)
    claimed = claim_next_outbox_jobs(
        db,
        tenant,
        action_types=SUPPORTED_ACTION_TYPES,
        limit=limit,
        lease_seconds=lease_seconds,
        now=current,
    )
    counts = {
        "promoted_campaigns": promoted,
        "claimed": len(claimed),
        "completed": 0,
        "suppressed": 0,
        "retried": 0,
        "skipped": 0,
        "failed": 0,
        "unknown": 0,
    }
    for job in claimed:
        if job.action_type == "campaign.delivery.send":
            outcome = _dispatch_campaign_delivery(db, tenant, job, settings=settings, transport=transport, now=current)
        elif job.action_type == "conversation.email.send":
            outcome = _dispatch_conversation_email(db, tenant, job, settings=settings, transport=transport, now=current)
        elif job.action_type == "conversation.human_reply.send":
            outcome = _dispatch_human_reply(db, tenant, job, transport=transport, now=current)
        elif job.action_type == "webhook.deliver":
            outcome = _dispatch_webhook_delivery(db, tenant, job, transport=transport, now=current)
        elif job.action_type == "notification.external.send":
            outcome = _dispatch_external_notification(db, tenant, job, settings=settings, transport=transport, now=current)
        else:
            fail_outbox_action(db, tenant, job.id, job.claim_token, error="unsupported_action_type", retryable=False, now=current)
            outcome = "failed"
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def run_worker_cycle(
    session_factory,
    *,
    settings: Settings,
    transport: OutboxTransport | None = None,
    now: datetime | None = None,
) -> dict:
    """Iterate active tenant runtimes fairly, isolating transactions and errors per tenant."""
    current = _utc_now(now)
    active_transport = transport or StdlibOutboxTransport(settings)
    summary = {
        "tenants_checked": 0,
        "tenants_failed": 0,
        "promoted_campaigns": 0,
        "workflow_runs_started": 0,
        "workflow_runs_resumed": 0,
        "claimed": 0,
        "completed": 0,
        "suppressed": 0,
        "retried": 0,
        "skipped": 0,
        "failed": 0,
        "unknown": 0,
    }

    with session_factory() as db:
        runtimes = list(
            db.scalars(
                select(TenantRuntime)
                .where(TenantRuntime.status == "active")
                .order_by(TenantRuntime.auth_tenant_id.asc())
            ).all()
        )
        tenants = [
            TenantContext(
                auth_tenant_id=rt.auth_tenant_id,
                tenant_slug=rt.tenant_slug,
                schema_name=rt.schema_name,
                tenant_code=rt.tenant_code,
                plan=rt.plan,
                status=rt.status,
            )
            for rt in runtimes
        ]

    for tenant in tenants:
        summary["tenants_checked"] += 1
        try:
            with session_factory() as tenant_db:
                wf_res = process_tenant_workflows(tenant_db, tenant, now=current)
                summary["workflow_runs_started"] += wf_res["runs_started"]
                summary["workflow_runs_resumed"] += wf_res["runs_resumed"]
                if not outbox_ready(tenant_db, tenant):
                    continue
                res = dispatch_tenant_outbox_batch(
                    tenant_db,
                    tenant,
                    settings=settings,
                    transport=active_transport,
                    limit=settings.worker_batch_size,
                    lease_seconds=settings.worker_lease_seconds,
                    now=current,
                )
                for key in ("promoted_campaigns", "claimed", "completed", "suppressed", "retried", "skipped", "failed", "unknown"):
                    summary[key] += res[key]
        except Exception:
            summary["tenants_failed"] += 1
            logger.exception("worker_tenant_cycle_failed auth_tenant_id=%s schema=%s", tenant.auth_tenant_id, tenant.schema_name)

    return summary
