from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import audit

from .models import UserSession


def evaluate_session_risk(session, request=None):
    flags = []
    previous = (
        UserSession.objects.filter(user=session.user)
        .exclude(id=session.id)
        .order_by("-created_at")
        .first()
    )
    if previous:
        if previous.user_agent != session.user_agent:
            flags.append("DEVICE_CHANGED")
        if previous.ip_address and session.ip_address and previous.ip_address != session.ip_address:
            flags.append("IP_CHANGED")
    else:
        flags.append("NEW_DEVICE")

    if flags:
        session.risk_flags = flags
        session.risk_score = min(100, 30 + (len(flags) * 20))
        session.save(update_fields=["risk_flags", "risk_score", "updated_at"])
        audit(AuditLog.Event.SESSION_RISK_DETECTED, request=request, user=session.user, tenant=session.tenant, session_id=session.id, flags=flags)
    return flags


def mark_refresh_reuse(session, request=None):
    session.status = UserSession.Status.COMPROMISED
    session.risk_flags = sorted(set(session.risk_flags + ["REFRESH_REUSE_DETECTED"]))
    session.risk_score = 100
    session.revoked_at = timezone.now()
    session.save(update_fields=["status", "risk_flags", "risk_score", "revoked_at", "updated_at"])
    audit(AuditLog.Event.SESSION_COMPROMISED, request=request, user=session.user, tenant=session.tenant, session_id=session.id)
    return session
