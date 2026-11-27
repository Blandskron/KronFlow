"""PRV-018: IAM data retention sweep (ContactMessage, LOGIN_FAILED audit emails, expired sessions, pending_purge tenants)."""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
import requests

from apps.audit.models import AuditLog
from apps.contact.models import ContactMessage
from apps.sessions.models import UserSession
from apps.tenants.models import Tenant


def execute_iam_retention(
    *,
    contact_days: int = 180,
    audit_email_days: int = 90,
    session_days: int = 30,
    now=None,
    purge_transport=None,
) -> dict:
    current = now or timezone.now()
    contact_cutoff = current - timedelta(days=contact_days)
    audit_cutoff = current - timedelta(days=audit_email_days)
    session_cutoff = current - timedelta(days=session_days)

    deleted_contacts, _ = ContactMessage.objects.filter(created_at__lt=contact_cutoff).delete()

    redacted_audit_emails = 0
    for log in AuditLog.objects.filter(event=AuditLog.Event.LOGIN_FAILED, created_at__lt=audit_cutoff):
        meta = dict(log.metadata or {})
        if "email" in meta and meta["email"] != "[REDACTED_RETENTION]":
            meta["email"] = "[REDACTED_RETENTION]"
            log.metadata = meta
            log.save(update_fields=["metadata"])
            redacted_audit_emails += 1

    deleted_sessions, _ = UserSession.objects.filter(
        expires_at__lt=session_cutoff,
    ).exclude(status=UserSession.Status.ACTIVE).delete()

    purged_tenants = 0
    purge_errors = 0
    due_tenants = list(
        Tenant.objects.filter(
            status=Tenant.Status.PENDING_PURGE,
            purge_after__isnull=False,
            purge_after__lte=current,
        )
    )
    sender = purge_transport or _call_operational_purge
    for tenant in due_tenants:
        try:
            if sender(tenant.id):
                tenant.delete()
                purged_tenants += 1
        except Exception:
            purge_errors += 1

    return {
        "deleted_contacts": deleted_contacts,
        "redacted_audit_emails": redacted_audit_emails,
        "deleted_sessions": deleted_sessions,
        "purged_tenants": purged_tenants,
        "purge_errors": purge_errors,
    }


def _call_operational_purge(tenant_id: int) -> bool:
    base_url = getattr(settings, "OPERATIONAL_SERVICE_URL", "").rstrip("/")
    token = getattr(settings, "OPERATIONAL_INTERNAL_TOKEN", "")
    if not base_url or not token:
        return False
    resp = requests.delete(
        f"{base_url}/internal/tenants/{tenant_id}/purge",
        headers={"X-Internal-Token": token},
        timeout=15,
    )
    return resp.status_code in (200, 404)


class Command(BaseCommand):
    help = "Run IAM retention cleanup for ContactMessage, LOGIN_FAILED audit emails, sessions, and pending_purge tenants."

    def add_arguments(self, parser):
        parser.add_argument("--contact-days", type=int, default=180)
        parser.add_argument("--audit-email-days", type=int, default=90)
        parser.add_argument("--session-days", type=int, default=30)

    def handle(self, *args, **options):
        result = execute_iam_retention(
            contact_days=options["contact_days"],
            audit_email_days=options["audit_email_days"],
            session_days=options["session_days"],
        )
        self.stdout.write(str(result))
