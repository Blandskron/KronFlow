from .models import AuditLog


def audit(event, request=None, user=None, tenant=None, **metadata):
    if request is not None:
        user = user or (request.user if getattr(request, "user", None) and request.user.is_authenticated else None)
        ip = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        correlation_id = getattr(request, "correlation_id", "")
    else:
        ip = None
        user_agent = ""
        correlation_id = ""
    return AuditLog.objects.create(
        event=event,
        user=user,
        tenant=tenant,
        ip_address=ip,
        user_agent=user_agent,
        correlation_id=correlation_id,
        metadata=metadata,
    )
