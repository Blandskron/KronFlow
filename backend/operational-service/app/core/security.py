import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
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


def hash_secret(secret: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt.encode("utf-8"), 180_000)
    return f"pbkdf2_sha256$180000${salt}${digest.hex()}"


def verify_secret(secret: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, digest = encoded.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt.encode("utf-8"), int(iterations))
    return hmac.compare_digest(candidate.hex(), digest)


def generate_ingest_key() -> str:
    return f"xik_{secrets.token_urlsafe(32)}"


def generate_tenant_code() -> str:
    return f"xt_{secrets.token_urlsafe(12).replace('-', '').replace('_', '').lower()[:16]}"


def load_public_key(settings: Settings) -> str:
    if settings.jwt_public_key:
        return settings.jwt_public_key.replace("\\n", "\n")
    if settings.jwt_public_key_path:
        path = Path(settings.jwt_public_key_path)
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


@dataclass(frozen=True)
class CurrentPrincipal:
    user_id: str
    tenant_id: int
    membership_id: str | None
    roles: list[str]
    permissions: list[str]
    subscription: dict[str, Any]
    raw_claims: dict[str, Any]

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.internal_token or not x_internal_token or not hmac.compare_digest(x_internal_token, settings.internal_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")


def get_current_principal(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    settings: Settings = Depends(get_settings),
) -> CurrentPrincipal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    public_key = load_public_key(settings)
    if not public_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="JWT public key is not configured")

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
    if not str(tenant_id).isascii() or not str(tenant_id).isdecimal() or int(tenant_id) < 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token has no tenant")

    principal = CurrentPrincipal(
        user_id=str(claims.get("user_id") or claims.get("sub") or ""),
        tenant_id=int(tenant_id),
        membership_id=str(claims.get("membership_id")) if claims.get("membership_id") else None,
        roles=list(claims.get("roles") or []),
        permissions=list(claims.get("permissions") or []),
        subscription=dict(claims.get("subscription") or {}),
        raw_claims=claims,
    )
    request.state.user = principal
    return principal


def require_permission(permission: str):
    def dependency(principal: CurrentPrincipal = Depends(get_current_principal)) -> CurrentPrincipal:
        if not principal.has_permission(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission}")
        return principal

    return dependency
