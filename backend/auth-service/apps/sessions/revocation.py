"""Fast JWT revocation markers in shared Redis (PRV-007).

Writes compact denylist / revocation-epoch keys read by operational-service and
agent-core so logout, session revocation, role changes, or tenant suspension
invalidate active access tokens immediately (<5s).
"""

import logging
import time

from django.conf import settings

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

logger = logging.getLogger(__name__)
KEY_PREFIX = "flowkron:jwt_revoked:"
DEFAULT_TTL_SECONDS = 86400


def _get_redis_client():
    redis_url = getattr(settings, "REDIS_URL", "") or ""
    if not redis_url or redis is None:
        return None
    try:
        return redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    except Exception:
        logger.warning("jwt_revocation_redis outcome=init_failed")
        return None


def _safe_set(key: str, value: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS, client=None) -> bool:
    conn = client if client is not None else _get_redis_client()
    if conn is None:
        return False
    try:
        conn.set(key, value, ex=max(60, int(ttl_seconds)))
        return True
    except Exception:
        logger.warning("jwt_revocation_redis outcome=write_failed key=%s", key)
        return False


def revoke_jti(jti: str | None, *, ttl_seconds: int = 3600, client=None) -> bool:
    if not jti:
        return False
    return _safe_set(f"{KEY_PREFIX}jti:{jti}", "1", ttl_seconds=ttl_seconds, client=client)


def revoke_session(session_id: int | str | None, *, ttl_seconds: int = DEFAULT_TTL_SECONDS, client=None) -> bool:
    if session_id is None or str(session_id) == "":
        return False
    return _safe_set(f"{KEY_PREFIX}session:{session_id}", "1", ttl_seconds=ttl_seconds, client=client)


def revoke_user_tokens(
    user_id: int | str | None,
    *,
    at_ts: float | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    client=None,
) -> bool:
    if user_id is None or str(user_id) == "":
        return False
    ts = str(int(at_ts if at_ts is not None else time.time()))
    return _safe_set(f"{KEY_PREFIX}user:{user_id}", ts, ttl_seconds=ttl_seconds, client=client)


def revoke_tenant_tokens(
    tenant_id: int | str | None,
    *,
    at_ts: float | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    client=None,
) -> bool:
    if tenant_id is None or str(tenant_id) == "":
        return False
    ts = str(int(at_ts if at_ts is not None else time.time()))
    return _safe_set(f"{KEY_PREFIX}tenant:{tenant_id}", ts, ttl_seconds=ttl_seconds, client=client)
