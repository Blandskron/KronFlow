from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import Settings, get_settings


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
