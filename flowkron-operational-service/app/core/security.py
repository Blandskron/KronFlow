import hashlib
import hmac
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import Settings, get_settings


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
