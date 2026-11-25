import asyncio
import json
from dataclasses import asdict
from typing import Protocol

from .email import EmailResult


class IdempotencyStore(Protocol):
    async def get(self, client_id: str, key: str) -> EmailResult | None:
        ...

    async def reserve(self, client_id: str, key: str) -> bool:
        ...

    async def complete(self, client_id: str, key: str, result: EmailResult) -> None:
        ...


class MemoryIdempotencyStore:
    def __init__(self):
        self._results: dict[tuple[str, str], EmailResult] = {}
        self._reserved: set[tuple[str, str]] = set()
        self._lock = asyncio.Lock()

    async def get(self, client_id: str, key: str) -> EmailResult | None:
        async with self._lock:
            return self._results.get((client_id, key))

    async def reserve(self, client_id: str, key: str) -> bool:
        async with self._lock:
            pair = (client_id, key)
            if pair in self._results or pair in self._reserved:
                return False
            self._reserved.add(pair)
            return True

    async def complete(self, client_id: str, key: str, result: EmailResult) -> None:
        async with self._lock:
            pair = (client_id, key)
            self._reserved.discard(pair)
            self._results[pair] = result


class RedisIdempotencyStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 86400):
        from redis.asyncio import Redis
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.ttl_seconds = ttl_seconds

    def _key(self, client_id: str, key: str) -> str:
        return f"email-gateway:idempotency:{client_id}:{key}"

    async def get(self, client_id: str, key: str) -> EmailResult | None:
        raw = await self.redis.get(self._key(client_id, key))
        if not raw:
            return None
        data = json.loads(raw)
        if data.get("status") == "processing":
            return None
        return EmailResult(**data)

    async def reserve(self, client_id: str, key: str) -> bool:
        return bool(await self.redis.set(self._key(client_id, key), json.dumps({"status": "processing"}), nx=True, ex=self.ttl_seconds))

    async def complete(self, client_id: str, key: str, result: EmailResult) -> None:
        await self.redis.set(self._key(client_id, key), json.dumps(asdict(result)), ex=self.ttl_seconds)

    async def close(self) -> None:
        await self.redis.aclose()


def build_idempotency_store(redis_url: str) -> IdempotencyStore:
    return RedisIdempotencyStore(redis_url) if redis_url else MemoryIdempotencyStore()
