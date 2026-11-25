import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from .config import Settings


@dataclass(frozen=True)
class ClientIdentity:
    client_id: str


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def authenticate_client(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> ClientIdentity:
    settings: Settings = request.app.state.settings
    token = bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "AUTH_REQUIRED", "message": "Credencial interna requerida."})
    for client_id, client in settings.clients.items():
        if client.active and secrets.compare_digest(token, client.api_key):
            return ClientIdentity(client_id=client_id)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "AUTH_INVALID", "message": "Credencial interna inválida."})


def authorize_sender(request: Request, identity: ClientIdentity, sender_key: str) -> None:
    client = request.app.state.settings.clients[identity.client_id]
    if sender_key not in client.allowed_senders:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "SENDER_FORBIDDEN", "message": "El cliente no está autorizado para ese remitente."})
