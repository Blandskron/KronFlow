"""Distributed Redis-backed ingest rate limiter with bounded in-memory fallback."""

from collections import OrderedDict, deque
import logging
import secrets
from threading import Lock
import time

from fastapi import Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.tenant_resolver import TenantContext, resolve_tenant_from_ingest_headers


logger = logging.getLogger("operational.rate_limit")


class IngestRateLimiter:
    """Sliding 60s window limiter per tenant_code using Redis when configured, else bounded memory."""

    def __init__(self, redis_url: str = "", *, window_seconds: int = 60, max_memory_tenants: int = 4096, redis_client=None):
        self.redis_url = redis_url.strip()
        self.window_seconds = max(1, int(window_seconds))
        self.max_memory_tenants = max(16, int(max_memory_tenants))
        self._redis = redis_client
        self._redis_failed_until = 0.0
        self._lock = Lock()
        self._windows: OrderedDict[str, deque[float]] = OrderedDict()

    def _get_redis(self):
        if self._redis is not None:
            return self._redis
        if not self.redis_url:
            return None
        from redis import Redis

        self._redis = Redis.from_url(self.redis_url, decode_responses=True, socket_timeout=1.5, socket_connect_timeout=1.5)
        return self._redis

    def _allow_redis(self, tenant_code: str, limit: int, now: float) -> bool | None:
        if self._redis is None and not self.redis_url:
            return None
        if now < self._redis_failed_until:
            return None
        try:
            client = self._get_redis()
            if client is None:
                return None
            key = f"kronflow:ingest_rl:{tenant_code}"
            cutoff = now - self.window_seconds
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, "-inf", cutoff)
            pipe.zcard(key)
            _, count = pipe.execute()
            if int(count) >= limit:
                return False
            member = f"{now:.6f}:{secrets.token_hex(4)}"
            pipe = client.pipeline()
            pipe.zadd(key, {member: now})
            pipe.expire(key, self.window_seconds + 5)
            pipe.execute()
            return True
        except Exception:
            self._redis_failed_until = now + 5.0
            logger.warning("ingest_rate_limit_redis_fallback tenant_code=%s", tenant_code)
            return None

    def _allow_memory(self, tenant_code: str, limit: int, now: float) -> bool:
        cutoff = now - self.window_seconds
        with self._lock:
            if tenant_code not in self._windows and len(self._windows) >= self.max_memory_tenants:
                stale = [k for k, q in self._windows.items() if not q or q[-1] <= cutoff]
                for k in stale:
                    del self._windows[k]
                while len(self._windows) >= self.max_memory_tenants:
                    self._windows.popitem(last=False)

            window = self._windows.get(tenant_code)
            if window is None:
                window = deque()
                self._windows[tenant_code] = window
            else:
                self._windows.move_to_end(tenant_code)

            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= limit:
                return False
            window.append(now)
            return True

    def allow(self, tenant_code: str, limit: int, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        redis_decision = self._allow_redis(tenant_code, limit, current)
        if redis_decision is not None:
            return redis_decision
        return self._allow_memory(tenant_code, limit, current)


_limiter_lock = Lock()
_limiter: IngestRateLimiter | None = None
_limiter_redis_url: str | None = None


def _get_limiter(settings: Settings) -> IngestRateLimiter:
    global _limiter, _limiter_redis_url
    with _limiter_lock:
        if _limiter is None or _limiter_redis_url != settings.redis_url:
            _limiter = IngestRateLimiter(settings.redis_url)
            _limiter_redis_url = settings.redis_url
        return _limiter


def enforce_ingest_rate_limit(
    tenant: TenantContext = Depends(resolve_tenant_from_ingest_headers),
    settings: Settings = Depends(get_settings),
) -> TenantContext:
    limiter = _get_limiter(settings)
    if not limiter.allow(tenant.tenant_code, settings.ingest_rate_limit_per_minute):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Tenant ingest rate limit exceeded")
    return tenant
