import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.tenant_resolver import TenantContext, resolve_tenant_from_ingest_headers


_windows: dict[str, deque[float]] = defaultdict(deque)


def enforce_ingest_rate_limit(
    tenant: TenantContext = Depends(resolve_tenant_from_ingest_headers),
    settings: Settings = Depends(get_settings),
) -> TenantContext:
    now = time.time()
    window = _windows[tenant.tenant_code]
    while window and window[0] <= now - 60:
        window.popleft()
    if len(window) >= settings.ingest_rate_limit_per_minute:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Tenant ingest rate limit exceeded")
    window.append(now)
    return tenant

