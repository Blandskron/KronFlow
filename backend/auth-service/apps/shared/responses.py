from rest_framework.response import Response

from apps.shared.middleware import current_request, error_envelope, success_envelope


def ok(data=None, status=200, message=None):
    request = current_request()
    if request is None:
        return Response({"success": True, "status": {"code": status, "message": message or "Request completed successfully"}, "data": data or {}, "meta": {}}, status=status)
    return Response(success_envelope(data or {}, status, request, message=message), status=status)


def api_error(*, status=400, detail="Request failed", error_code="ERROR", errors=None):
    request = current_request()
    if request is None:
        payload = {
            "type": f"urn:flowkron:problem:{str(error_code).lower()}",
            "title": "Request Error",
            "status": status,
            "detail": str(detail),
            "instance": "",
            "error_code": str(error_code),
            "errors": errors or [],
            "meta": {},
        }
    else:
        payload = error_envelope(status_code=status, request=request, detail=detail, error_code=error_code, errors=errors or [])
    return Response(payload, status=status)
