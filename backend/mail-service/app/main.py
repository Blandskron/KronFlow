from contextlib import asynccontextmanager
import json
import logging
import time
import uuid

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.openapi.utils import get_openapi

from .config import ConfigurationError, get_settings, validate_runtime_settings
from .email import EmailResult
from .idempotency import build_idempotency_store
from .models import EmailSendRequest, EmailSendResponse, ErrorDetail, LegacyMailRequest
from .rate_limit import enforce_rate_limit, RateLimiter
from .resend_provider import ProviderError, ResendEmailProvider
from .security import ClientIdentity, authenticate_client, authorize_sender
from .service import EmailService
from .webhooks import build_webhook_event_store, handle_webhook

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("email-gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    validate_runtime_settings(settings)
    client = httpx.AsyncClient(base_url=settings.resend_base_url.rstrip("/"), timeout=settings.resend_timeout_seconds)
    store = build_idempotency_store(settings.redis_url)
    webhook_store = build_webhook_event_store(settings.redis_url)
    app.state.settings = settings
    app.state.provider = ResendEmailProvider(settings, client)
    app.state.idempotency = store
    app.state.webhook_store = webhook_store
    app.state.email_service = EmailService(settings, app.state.provider, store)
    app.state.rate_limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)
    app.state.audit_logger = logging.getLogger("email-gateway.audit")
    yield
    await client.aclose()
    if hasattr(store, "close"):
        await store.close()
    if hasattr(webhook_store, "close"):
        await webhook_store.close()


app = FastAPI(
    title="Blandskron Email Gateway",
    description="API centralizada de correos transaccionales mediante proveedores HTTP.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed request_id=%s path=%s", request_id, request.url.path)
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info("request_completed request_id=%s path=%s status=%s duration_ms=%s", request_id, request.url.path, response.status_code, round((time.perf_counter() - started) * 1000, 2))
    return response


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}


@app.get("/ready", tags=["Health"])
async def ready(request: Request):
    settings = request.app.state.settings
    if not settings.resend_api_key or not settings.senders or not settings.clients:
        raise HTTPException(status_code=503, detail={"code": "NOT_READY", "message": "El proveedor de correo no está configurado."})
    return {"status": "ready", "provider": "resend", "senders_configured": len(settings.senders)}


async def send_email(request: Request, payload: EmailSendRequest, identity: ClientIdentity):
    authorize_sender(request, identity, payload.sender_key)
    await enforce_rate_limit(request, identity.client_id, payload.sender_key)
    try:
        result, duplicate = await request.app.state.email_service.send(identity.client_id, payload)
    except ConfigurationError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "message": str(exc)}) from exc
    except ProviderError as exc:
        if exc.code == "IDEMPOTENCY_IN_PROGRESS":
            raise HTTPException(status_code=409, detail={"code": exc.code, "message": "La operación ya está en proceso."}) from exc
        raise HTTPException(status_code=502, detail={"code": exc.code, "message": "No fue posible procesar el correo."}) from exc
    return EmailSendResponse(success=result.success, status="accepted" if result.success else result.status, message_id=result.message_id, recipients=len(payload.to), provider=result.provider)


@app.post("/api/v1/emails/send", response_model=EmailSendResponse, tags=["Emails"])
async def send_email_endpoint(request: Request, payload: EmailSendRequest, identity: ClientIdentity = Depends(authenticate_client)):
    return await send_email(request, payload, identity)


@app.post("/api/v1/webhooks/resend", tags=["Webhooks"])
async def resend_webhook(request: Request):
    return await handle_webhook(request)


@app.post("/mail", deprecated=True, response_model=EmailSendResponse, tags=["Legacy"])
async def legacy_mail(request: Request, payload: LegacyMailRequest, identity: ClientIdentity = Depends(authenticate_client)):
    if not request.app.state.settings.enable_legacy_mail_endpoint:
        raise HTTPException(status_code=404, detail={"code": "LEGACY_DISABLED", "message": "Ruta no disponible."})
    logger.warning("deprecated_endpoint path=/mail client_id=%s", identity.client_id)
    return await send_email(request, EmailSendRequest(
        sender_key=payload.sender_key,
        to=payload.to,
        subject=payload.subject,
        html=payload.html,
        text=payload.text,
        reply_to=payload.reply_to,
        idempotency_key=payload.idempotency_key,
    ), identity)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    schema["components"]["securitySchemes"] = {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "internal"}}
    for path, methods in schema.get("paths", {}).items():
        if path in {"/api/v1/emails/send", "/mail"}:
            for operation in methods.values():
                if isinstance(operation, dict):
                    operation["security"] = [{"bearerAuth": []}]
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi
