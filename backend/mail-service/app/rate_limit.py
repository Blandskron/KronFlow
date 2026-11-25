import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


@dataclass
class RateLimiter:
    limit: int
    window_seconds: int

    def __post_init__(self):
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> int | None:
        now = time.monotonic()
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= now - self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = max(1, int(events[0] + self.window_seconds - now))
                return retry_after
            events.append(now)
            return None


async def enforce_rate_limit(request: Request, client_id: str, sender_key: str) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    ip = request.client.host if request.client else "unknown"
    retry_after = await limiter.check(f"{client_id}:{sender_key}:{ip}")
    if retry_after is not None:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "RATE_LIMITED", "message": "Límite de solicitudes excedido."}, headers={"Retry-After": str(retry_after)})
