from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import Settings, get_settings

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

logger = logging.getLogger(__name__)
REVOCATION_KEY_PREFIX = "flowkron:jwt_revoked:"
_REVOCATION_CLIENTS: dict[str, Any] = {}


def _get_revocation_redis(redis_url: str):
    if not redis_url or redis is None:
        return None
    client = _REVOCATION_CLIENTS.get(redis_url)
    if client is None:
        client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        _REVOCATION_CLIENTS[redis_url] = client
    return client


def is_jwt_revoked(claims: dict[str, Any], settings: Settings, *, redis_client: Any = None) -> bool:
    """Check shared Redis fast-revocation markers for jti, session_id, user_id, and tenant_id (PRV-007)."""
    client = redis_client if redis_client is not None else _get_revocation_redis(settings.redis_url)
    if client is None:
        return False

    jti = claims.get("jti")
    session_id = claims.get("session_id")
    user_id = claims.get("user_id") or claims.get("sub")
    tenant_id = claims.get("tenant_id")
    iat = claims.get("iat")
    try:
        iat_val = float(iat) if iat is not None else 0.0
    except (TypeError, ValueError):
        iat_val = 0.0

    keys: list[tuple[str, str]] = []
    if jti:
        keys.append(("exact", f"{REVOCATION_KEY_PREFIX}jti:{jti}"))
    if session_id:
        keys.append(("exact", f"{REVOCATION_KEY_PREFIX}session:{session_id}"))
    if user_id:
        keys.append(("epoch", f"{REVOCATION_KEY_PREFIX}user:{user_id}"))
    if tenant_id:
        keys.append(("epoch", f"{REVOCATION_KEY_PREFIX}tenant:{tenant_id}"))
    if not keys:
        return False

    try:
        values = client.mget([k for _, k in keys])
    except Exception:
        logger.warning("jwt_revocation_check outcome=redis_unavailable")
        return False

    for (kind, _key), raw in zip(keys, values):
        if raw is None:
            continue
        if kind == "exact":
            return True
        try:
            if iat_val <= float(raw):
                return True
        except (TypeError, ValueError):
            return True
    return False


@dataclass(frozen=True)
class CurrentPrincipal:
    user_id: str
    tenant_id: str
    roles: list[str]
    permissions: list[str]
    raw_claims: dict[str, Any]


def load_public_key(settings: Settings) -> str:
    if settings.jwt_public_key:
        return settings.jwt_public_key.replace("\\n", "\n")
    if settings.jwt_public_key_path:
        path = Path(settings.jwt_public_key_path)
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


def get_current_principal(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    settings: Settings = Depends(get_settings),
) -> CurrentPrincipal:
    public_key = load_public_key(settings)
    if authorization and authorization.lower().startswith("bearer ") and public_key:
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = jwt.decode(
                token,
                public_key,
                algorithms=[settings.jwt_algorithm],
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
                options={"require": ["exp", "iat", "jti", "token_type", "user_id", "tenant_id"]},
            )
            if claims["token_type"] != "access":
                raise jwt.InvalidTokenError("Expected an access token")
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc
        if is_jwt_revoked(claims, settings):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token has no tenant")
        principal = CurrentPrincipal(
            user_id=str(claims.get("user_id") or claims.get("sub") or ""),
            tenant_id=str(tenant_id),
            roles=list(claims.get("roles") or []),
            permissions=list(claims.get("permissions") or []),
            raw_claims=claims,
        )
        request.state.user = principal
        return principal

    if not authorization and settings.environment == "local" and settings.allow_insecure_tenant_header and x_tenant_id:
        principal = CurrentPrincipal(user_id="local-dev", tenant_id=x_tenant_id, roles=["local"], permissions=["*"], raw_claims={})
        request.state.user = principal
        return principal

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authenticated tenant")
