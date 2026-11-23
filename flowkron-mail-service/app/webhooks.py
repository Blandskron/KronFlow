import base64
import hashlib
import hmac
import json
import time

from fastapi import HTTPException, Request, status

_seen_events: set[str] = set()


def verify_resend_signature(body: bytes, secret: str, svix_id: str | None, timestamp: str | None, signature: str | None) -> bool:
    if not secret or not svix_id or not timestamp or not signature:
        return False
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
        encoded_secret = secret.removeprefix("whsec_")
        signing_secret = base64.b64decode(encoded_secret)
        signed = f"{svix_id}.{timestamp}.".encode() + body
        expected = base64.b64encode(hmac.new(signing_secret, signed, hashlib.sha256).digest()).decode()
        return any(hmac.compare_digest(value.removeprefix("v1,"), expected) for value in signature.split(" "))
    except (ValueError, TypeError):
        return False


async def handle_webhook(request: Request) -> dict:
    body = await request.body()
    if not verify_resend_signature(
        body,
        request.app.state.settings.resend_webhook_secret,
        request.headers.get("svix-id"),
        request.headers.get("svix-timestamp"),
        request.headers.get("svix-signature"),
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "WEBHOOK_SIGNATURE_INVALID", "message": "Firma inválida."})
    event_id = request.headers.get("svix-id", "")
    if event_id in _seen_events:
        return {"success": True, "duplicate": True}
    _seen_events.add(event_id)
    payload = json.loads(body or b"{}")
    request.app.state.audit_logger.info("resend_webhook event_id=%s event_type=%s", event_id, payload.get("type"))
    return {"success": True, "duplicate": False}
