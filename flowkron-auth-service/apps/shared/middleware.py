import json
import re
import uuid
from contextvars import ContextVar

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

_current_request: ContextVar[object | None] = ContextVar("current_request", default=None)


def current_request():
    return _current_request.get()


def request_meta(request):
    user = getattr(request, "user", None)
    auth = getattr(request, "auth", None)
    tenant_id = None
    if isinstance(auth, dict):
        tenant_id = auth.get("tenant_id")
    return {
        "api_version": "v1",
        "service": "auth-service",
        "environment": "local" if settings.DEBUG else "production",
        "tenant_id": str(tenant_id) if tenant_id is not None else None,
        "user_id": str(user.id) if getattr(user, "is_authenticated", False) else None,
        "request_id": getattr(request, "request_id", ""),
        "correlation_id": getattr(request, "correlation_id", ""),
        "trace_id": request.headers.get("X-Trace-ID"),
        "timestamp": timezone.now().isoformat().replace("+00:00", "Z"),
    }


def success_envelope(data, status_code, request, message=None):
    return {
        "success": True,
        "status": {"code": status_code, "message": message or "Request completed successfully"},
        "data": data if data is not None else {},
        "meta": request_meta(request),
    }


def error_envelope(*, status_code, request, detail, error_code, errors=None, title=None):
    return {
        "type": f"urn:flowkron:problem:{str(error_code).lower().replace('_', '-')}",
        "title": title or _default_error_title(status_code),
        "status": status_code,
        "detail": str(detail),
        "instance": request.path,
        "error_code": normalize_error_code(error_code, status_code),
        "errors": errors or [],
        "meta": {
            "api_version": "v1",
            "service": "auth-service",
            "tenant_id": request_meta(request)["tenant_id"],
            "request_id": getattr(request, "request_id", ""),
            "correlation_id": getattr(request, "correlation_id", ""),
            "timestamp": timezone.now().isoformat().replace("+00:00", "Z"),
        },
    }


def normalize_error_code(code, status_code):
    raw = str(code or "ERROR").upper().replace("-", "_").replace(" ", "_")
    raw = re.sub(r"[^A-Z0-9_]+", "_", raw).strip("_") or "ERROR"
    raw = re.sub(r"_+", "_", raw)
    if raw.startswith("AUTH_") and f"_{status_code}_" in raw:
        return raw
    if raw.startswith("PLATFORM_") and f"_{status_code}_" in raw:
        return raw
    return f"AUTH_{status_code}_{raw}"


def _default_error_title(status_code):
    if status_code == 400:
        return "Bad Request"
    if status_code == 401:
        return "Unauthorized"
    if status_code == 403:
        return "Forbidden"
    if status_code == 404:
        return "Not Found"
    if status_code == 429:
        return "Too Many Requests"
    if status_code >= 500:
        return "Server Error"
    return "Request Error"


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_request.set(request)
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        correlation_id = request.headers.get("X-Correlation-ID") or request_id
        request.request_id = request_id
        request.correlation_id = correlation_id
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            response["X-Correlation-ID"] = correlation_id
            return response
        finally:
            _current_request.reset(token)


class ApiContractMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/api/v1/"):
            return response
        content_type = response.get("Content-Type", "")
        if "application/json" not in content_type:
            return response

        try:
            payload = json.loads(response.content.decode(response.charset or "utf-8") or "{}")
        except (AttributeError, json.JSONDecodeError, UnicodeDecodeError):
            return response

        if _is_standard_success(payload) or _is_standard_error(payload):
            return response

        status_code = response.status_code
        if status_code < 400:
            data = payload.get("data", {}) if isinstance(payload, dict) and payload.get("success") is True and "data" in payload else payload
            wrapped = success_envelope(data, status_code, request)
        else:
            wrapped = _legacy_error_to_contract(payload, status_code, request)

        new_response = JsonResponse(wrapped, status=status_code)
        for header in ("X-Request-ID", "X-Correlation-ID"):
            if response.get(header):
                new_response[header] = response[header]
        return new_response


def _is_standard_success(payload):
    return isinstance(payload, dict) and payload.get("success") is True and all(key in payload for key in ["status", "data", "meta"])


def _is_standard_error(payload):
    return isinstance(payload, dict) and all(key in payload for key in ["type", "title", "status", "detail", "error_code", "errors", "meta"])


def _legacy_error_to_contract(payload, status_code, request):
    if isinstance(payload, dict):
        detail = payload.get("message") or payload.get("detail") or _first_detail(payload) or "Request failed"
        error_code = payload.get("code") or payload.get("error_code") or "ERROR"
        errors = _errors_from_payload(payload)
    else:
        detail = str(payload)
        error_code = "ERROR"
        errors = []
    return error_envelope(status_code=status_code, request=request, detail=detail, error_code=error_code, errors=errors)


def _first_detail(payload):
    for value in payload.values():
        if isinstance(value, list) and value:
            return value[0]
        if isinstance(value, dict):
            nested = _first_detail(value)
            if nested:
                return nested
        if isinstance(value, str):
            return value
    return None


def _errors_from_payload(payload):
    details = payload.get("details") if isinstance(payload, dict) else None
    source = details if isinstance(details, dict) else payload
    errors = []
    if isinstance(source, dict):
        for field, value in source.items():
            if field in {"success", "code", "message", "detail", "error_code"}:
                continue
            if isinstance(value, list):
                for item in value:
                    errors.append({"field": field, "code": "invalid", "message": str(item)})
            elif isinstance(value, dict):
                errors.append({"field": field, "code": "invalid", "message": json.dumps(value, ensure_ascii=False)})
            else:
                errors.append({"field": field, "code": "invalid", "message": str(value)})
    return errors
