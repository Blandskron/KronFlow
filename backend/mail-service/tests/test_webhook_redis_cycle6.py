"""PRV-022 / QG-6: Distributed Redis webhook deduplication and production guard tests."""

import asyncio
import pytest

from app.webhooks import RedisWebhookEventStore, build_webhook_event_store


class _FakeAsyncRedis:
    def __init__(self):
        self.keys: dict[str, tuple[str, int | None]] = {}

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None):
        if nx and key in self.keys:
            return False
        self.keys[key] = (value, ex)
        return True

    async def aclose(self):
        return None


def test_prv022_redis_webhook_dedup_with_ttl_and_production_guard():
    fake = _FakeAsyncRedis()
    store = RedisWebhookEventStore("redis://unused", ttl_seconds=3600, redis_client=fake)
    assert asyncio.run(store.mark_if_new("svix-evt-1")) is True
    assert asyncio.run(store.mark_if_new("svix-evt-1")) is False
    assert fake.keys["email-gateway:webhook:svix-evt-1"] == ("1", 3600)

    with pytest.raises(RuntimeError, match="REDIS_URL is required"):
        build_webhook_event_store("", allow_memory_fallback=False)
