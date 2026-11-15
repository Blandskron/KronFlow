from rest_framework.views import exception_handler
from django.http import JsonResponse

from apps.shared.middleware import current_request, error_envelope


def standard_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response

    request = context.get("request") or current_request()
    code = getattr(exc, "default_code", "ERROR")
    message = getattr(exc, "detail", "Error")
    errors = _flatten_errors(response.data)
    if request is not None:
        response.data = error_envelope(
            status_code=response.status_code,
            request=request,
            detail=message,
            error_code=code,
            errors=errors,
        )
    return response


def _flatten_errors(data, prefix=None):
    errors = []
    if isinstance(data, dict):
        for field, value in data.items():
            nested_field = f"{prefix}.{field}" if prefix else field
            errors.extend(_flatten_errors(value, nested_field))
    elif isinstance(data, list):
        for value in data:
            errors.extend(_flatten_errors(value, prefix))
    else:
        errors.append({"field": prefix, "code": "invalid", "message": str(data)})
    return errors


def csrf_failure(request, reason=""):
    return JsonResponse(
        error_envelope(
            status_code=403,
            request=request,
            detail=reason or "CSRF validation failed.",
            error_code="PLATFORM_403_CSRF_FAILED",
            errors=[{"field": None, "code": "csrf_failed", "message": reason or "CSRF validation failed."}],
        ),
        status=403,
    )
