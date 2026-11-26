import asyncio
import base64
from collections import OrderedDict
import hashlib
import hmac
import json
import time
from typing import Protocol

from fastapi import HTTPException, Request, status


class WebhookEventStore(Protocol):
    async def mark_if_new(self, event_id: str) -> bool:
        ...


class MemoryWebhookEventStore:
    def __init__(self, max_entries: int = 10_000):
        self.max_entries = max(100, int(max_entries))
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._lock = asyncio.Lock()

    async def mark_if_new(self, event_id: str) -> bool:
        async with self._lock:
            if event_id in self._seen:
                self._seen.move_to_end(event_id)
                return False
            self._seen[event_id] = None
            while len(self._seen) > self.max_entries:
                self._seen.popitem(last=False)
            return True


class RedisWebhookEventStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 604_800, redis_client=None):
        if redis_client is not None:
            self.redis = redis_client
        else:
            from redis.asyncio import Redis

            self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.ttl_seconds = max(60, int(ttl_seconds))

    async def mark_if_new(self, event_id: str) -> bool:
        key = f"email-gateway:webhook:{event_id}"
        return bool(await self.redis.set(key, "1", nx=True, ex=self.ttl_seconds))

    async def close(self) -> None:
        await self.redis.aclose()


def build_webhook_event_store(redis_url: str) -> WebhookEventStore:
    return RedisWebhookEventStore(redis_url) if redis_url else MemoryWebhookEventStore()


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
    store = getattr(request.app.state, "webhook_store", None)
    if store is None:
        store = MemoryWebhookEventStore()
        request.app.state.webhook_store = store
    if not await store.mark_if_new(event_id):
        return {"success": True, "duplicate": True}
    payload = json.loads(body or b"{}")
    request.app.state.audit_logger.info("resend_webhook event_id=%s event_type=%s", event_id, payload.get("type"))
    return {"success": True, "duplicate": False}
