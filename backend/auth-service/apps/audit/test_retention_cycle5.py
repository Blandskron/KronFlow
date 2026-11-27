"""PRV-018 & PRV-019 / QG-5: IAM retention sweep, pending_purge tenant purge, and PII log filter tests."""

from datetime import timedelta
import logging

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.audit.management.commands.run_iam_retention import execute_iam_retention
from apps.audit.models import AuditLog
from apps.contact.models import ContactMessage
from apps.shared.logging_filters import PiiRedactingLogFilter, sanitize_log_text
from apps.tenants.models import Tenant


class Cycle5IamRetentionAndLoggingTests(TestCase):
    def test_prv018_iam_retention_purges_old_contacts_redacts_login_emails_and_purges_due_tenants(self):
        now = timezone.now()
        old_msg = ContactMessage.objects.create(
            name="Antiguo", email="old@example.test", message="Hola", accept_terms=True,
        )
        ContactMessage.objects.filter(pk=old_msg.pk).update(created_at=now - timedelta(days=200))
        fresh_msg = ContactMessage.objects.create(
            name="Reciente", email="fresh@example.test", message="Hola", accept_terms=True,
        )

        old_log = AuditLog.objects.create(
            event=AuditLog.Event.LOGIN_FAILED,
            metadata={"email": "failed.user@example.test"},
        )
        AuditLog.objects.filter(pk=old_log.pk).update(created_at=now - timedelta(days=120))

        due_tenant = Tenant.objects.create(
            name="Expired Corp",
            legal_name="Expired Corp SpA",
            status=Tenant.Status.PENDING_PURGE,
            pending_purge_at=now - timedelta(days=31),
            purge_after=now - timedelta(days=1),
        )
        purged_ids: list[int] = []
        result = execute_iam_retention(
            contact_days=180,
            audit_email_days=90,
            now=now,
            purge_transport=lambda tid: purged_ids.append(tid) or True,
        )

        self.assertEqual(result["deleted_contacts"], 1)
        self.assertEqual(result["redacted_audit_emails"], 1)
        self.assertEqual(result["purged_tenants"], 1)
        self.assertEqual(purged_ids, [due_tenant.id])
        self.assertTrue(ContactMessage.objects.filter(pk=fresh_msg.pk).exists())
        old_log.refresh_from_db()
        self.assertEqual(old_log.metadata["email"], "[REDACTED_RETENTION]")
        self.assertFalse(Tenant.objects.filter(pk=due_tenant.id).exists())

    def test_prv019_log_filter_redacts_email_rut_and_bearer_token(self):
        raw = "Login failed for user@acme.cl RUT 12.345.678-5 Bearer eyJhbGciOiJSUzI1NiJ9.payload.sig"
        sanitized = sanitize_log_text(raw)
        self.assertNotIn("user@acme.cl", sanitized)
        self.assertNotIn("12.345.678-5", sanitized)
        self.assertNotIn("eyJhbGciOiJSUzI1NiJ9", sanitized)
        self.assertIn("[REDACTED_EMAIL]", sanitized)
        self.assertIn("[REDACTED_RUT]", sanitized)
        self.assertIn("Bearer [REDACTED_TOKEN]", sanitized)

        filt = PiiRedactingLogFilter()
        rec = logging.LogRecord("test", logging.INFO, __file__, 1, "User %s", ("secret@acme.cl",), None)
        self.assertTrue(filt.filter(rec))
        self.assertEqual(rec.getMessage(), "User [REDACTED_EMAIL]")
