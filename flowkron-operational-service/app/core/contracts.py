import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings


SKIP_CONTRACT_PATHS = {"/openapi.json", "/docs", "/redoc"}


def request_meta(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    tenant = getattr(request.state, "tenant", None)
    return {
        "api_version": "v1",
        "service": "operational-service",
        "environment": get_settings().environment,
        "tenant_id": str(getattr(tenant, "auth_tenant_id", None) or getattr(tenant, "tenant_id", None) or getattr(user, "tenant_id", None) or "") or None,
        "user_id": str(getattr(user, "user_id", None) or "") or None,
        "request_id": getattr(request.state, "request_id", ""),
        "correlation_id": getattr(request.state, "correlation_id", ""),
        "trace_id": request.headers.get("X-Trace-ID"),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def success_envelope(data: Any, status_code: int, request: Request, message: str | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "status": {"code": status_code, "message": message or "Request completed successfully"},
        "data": data if data is not None else {},
        "meta": request_meta(request),
    }


def error_envelope(
    *,
    status_code: int,
    request: Request,
    detail: Any,
    error_code: str = "ERROR",
    errors: list[dict[str, Any]] | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_error_code(error_code, status_code)
    return {
        "type": f"urn:flowkron:problem:{normalized.lower().replace('_', '-')}",
        "title": title or default_error_title(status_code),
        "status": status_code,
        "detail": str(detail),
        "instance": request.url.path,
        "error_code": normalized,
        "errors": errors or [],
        "meta": {
            "api_version": "v1",
            "service": "operational-service",
            "tenant_id": request_meta(request)["tenant_id"],
            "request_id": getattr(request.state, "request_id", ""),
            "correlation_id": getattr(request.state, "correlation_id", ""),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }


def normalize_error_code(code: str, status_code: int) -> str:
    raw = str(code or "ERROR").upper().replace("-", "_").replace(" ", "_")
    raw = re.sub(r"[^A-Z0-9_]+", "_", raw).strip("_") or "ERROR"
    raw = re.sub(r"_+", "_", raw)
    if raw.startswith("OPERATIONAL_") and f"_{status_code}_" in raw:
        return raw
    if raw.startswith("PLATFORM_") and f"_{status_code}_" in raw:
        return raw
    return f"OPERATIONAL_{status_code}_{raw}"


def default_error_title(status_code: int) -> str:
    return {
        400: "Bad Request",
        401: "Unauthorized",
        402: "Payment Required",
        403: "Forbidden",
        404: "Not Found",
        422: "Validation Error",
        429: "Too Many Requests",
        501: "Not Implemented",
        502: "Bad Gateway",
        503: "Service Unavailable",
    }.get(status_code, "Server Error" if status_code >= 500 else "Request Error")


async def api_contract_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.correlation_id = request.headers.get("X-Correlation-ID") or request.state.request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Correlation-ID"] = request.state.correlation_id

    if request.url.path in SKIP_CONTRACT_PATHS or not _is_json_response(response):
        return response

    if hasattr(response, "body_iterator"):
        body = b"".join([chunk async for chunk in response.body_iterator])
    else:
        body = getattr(response, "body", b"")
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return Response(content=body, status_code=response.status_code, headers=_response_headers(response), media_type=response.media_type)

    if is_standard_success(payload) or is_standard_error(payload):
        return JSONResponse(content=payload, status_code=response.status_code, headers=_response_headers(response))

    if response.status_code < 400:
        wrapped = success_envelope(payload, response.status_code, request)
    else:
        wrapped = error_envelope(
            status_code=response.status_code,
            request=request,
            detail=_detail_from_payload(payload),
            error_code=_code_from_payload(payload),
            errors=_errors_from_payload(payload),
        )
    return JSONResponse(content=wrapped, status_code=response.status_code, headers=_response_headers(response))


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        content=error_envelope(
            status_code=exc.status_code,
            request=request,
            detail=exc.detail,
            error_code=str(exc.detail).upper().replace(" ", "_") if exc.detail else "HTTP_EXCEPTION",
        ),
        status_code=exc.status_code,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {
            "field": ".".join(str(part) for part in error.get("loc", [])),
            "code": error.get("type", "validation_error"),
            "message": error.get("msg", "Invalid value"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        content=error_envelope(
            status_code=422,
            request=request,
            detail="The request contains invalid fields.",
            error_code="PLATFORM_422_VALIDATION_ERROR",
            errors=errors,
            title="Validation Error",
        ),
        status_code=422,
    )


def is_standard_success(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("success") is True and all(key in payload for key in ["status", "data", "meta"])


def is_standard_error(payload: Any) -> bool:
    return isinstance(payload, dict) and all(key in payload for key in ["type", "title", "status", "detail", "error_code", "errors", "meta"])


def _is_json_response(response) -> bool:
    return "application/json" in response.headers.get("content-type", "")


def _response_headers(response) -> dict[str, str]:
    return {key: value for key, value in response.headers.items() if key.lower() not in {"content-length", "content-type"}}


def _detail_from_payload(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("message") or payload.get("detail") or payload)
    return str(payload)


def _code_from_payload(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("code") or payload.get("error_code") or payload.get("detail") or "ERROR")
    return "ERROR"


def _errors_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    detail = payload.get("detail")
    if isinstance(detail, list):
        return [
            {
                "field": ".".join(str(part) for part in item.get("loc", [])) if isinstance(item, dict) else None,
                "code": item.get("type", "invalid") if isinstance(item, dict) else "invalid",
                "message": item.get("msg", str(item)) if isinstance(item, dict) else str(item),
            }
            for item in detail
        ]
    return []
