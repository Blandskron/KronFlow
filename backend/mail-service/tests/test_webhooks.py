import base64
import hashlib
import hmac
import json
import time

import pytest

from app.main import app
from app.webhooks import RedisWebhookEventStore


def _sign_svix(secret: str, svix_id: str, timestamp: str, body: bytes) -> str:
    raw_secret = base64.b64decode(secret.removeprefix("whsec_"))
    mac = hmac.new(raw_secret, f"{svix_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    return f"v1,{base64.b64encode(mac).decode()}"


@pytest.mark.asyncio
async def test_resend_webhook_signature_and_dedup(client):
    secret = f"whsec_{base64.b64encode(b'super-secret-signing-key-32bytes').decode()}"
    app.state.settings.resend_webhook_secret = secret
    body = json.dumps({"type": "email.delivered", "data": {"email_id": "msg-1"}}).encode()
    ts = str(int(time.time()))
    sig = _sign_svix(secret, "svix_evt_1", ts, body)

    bad = await client.post(
        "/api/v1/webhooks/resend",
        content=body,
        headers={"svix-id": "svix_evt_1", "svix-timestamp": ts, "svix-signature": "v1,invalid"},
    )
    assert bad.status_code == 401

    first = await client.post(
        "/api/v1/webhooks/resend",
        content=body,
        headers={"svix-id": "svix_evt_1", "svix-timestamp": ts, "svix-signature": sig},
    )
    assert first.status_code == 200
    assert first.json() == {"success": True, "duplicate": False}

    dup = await client.post(
        "/api/v1/webhooks/resend",
        content=body,
        headers={"svix-id": "svix_evt_1", "svix-timestamp": ts, "svix-signature": sig},
    )
    assert dup.status_code == 200
    assert dup.json() == {"success": True, "duplicate": True}


@pytest.mark.asyncio
async def test_redis_webhook_event_store_deduplicates_with_ttl():
    class FakeAsyncRedis:
        def __init__(self):
            self.keys = {}

        async def set(self, key, value, nx=False, ex=None):
            if nx and key in self.keys:
                return False
            self.keys[key] = (value, ex)
            return True

        async def aclose(self):
            return None

    fake = FakeAsyncRedis()
    store = RedisWebhookEventStore("redis://unused:6379/0", ttl_seconds=3600, redis_client=fake)
    assert await store.mark_if_new("evt-redis-1") is True
    assert await store.mark_if_new("evt-redis-1") is False
    assert fake.keys["email-gateway:webhook:evt-redis-1"] == ("1", 3600)
    await store.close()
