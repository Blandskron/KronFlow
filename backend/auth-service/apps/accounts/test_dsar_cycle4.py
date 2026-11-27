"""PRV-015 / QG-4: IAM user DSAR (/me/export, /me/erase) and ContactMessage DSAR tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.contact.models import ContactMessage
from apps.rbac.models import MembershipRole, TenantRole
from apps.tenants.models import TenantMembership
from apps.tenants.services import create_owned_tenant


class IamDsarCycle4Tests(TestCase):
    def _make_user(self, email: str, *, is_staff: bool = False):
        user = get_user_model().objects.create_user(
            username=email,
            email=email,
            password="a-very-safe-password-123",
            is_staff=is_staff,
        )
        user.profile.display_name = "Usuario Real"
        user.profile.phone = "+56911112222"
        user.profile.email_verified_at = timezone.now()
        user.profile.save(update_fields=["display_name", "phone", "email_verified_at", "updated_at"])
        return user

    def test_me_export_and_erase_protects_last_owner_and_anonymizes_non_last_owner(self):
        owner = self._make_user("dsar-owner@example.com")
        member = self._make_user("dsar-member@example.com")
        tenant, _ = create_owned_tenant(owner, "DSAR Corp")
        mem = TenantMembership.objects.create(user=member, tenant=tenant, status=TenantMembership.Status.ACTIVE)
        MembershipRole.objects.create(membership=mem, role=TenantRole.objects.get(tenant=tenant, code="VIEWER"))

        client = APIClient()
        client.force_authenticate(user=owner)

        # Export returns user profile, memberships, sessions, and audit events without password hash.
        exp = client.get("/api/v1/auth/me/export/")
        self.assertEqual(exp.status_code, 200)
        exp_data = exp.json()["data"]
        self.assertEqual(exp_data["user"]["email"], "dsar-owner@example.com")
        self.assertNotIn("password", exp_data["user"])

        # Unconfirmed erasure is rejected (422).
        unconf = client.post("/api/v1/auth/me/erase/", {"confirmed": False}, format="json")
        self.assertEqual(unconf.status_code, 422)

        # Sole active TENANT_OWNER cannot erase account (409).
        blocked = client.post("/api/v1/auth/me/erase/", {"confirmed": True}, format="json")
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("LAST_OWNER_ERASURE_DENIED", str(blocked.json()))

        # Non-last-owner member CAN erase and gets fully anonymized.
        client.force_authenticate(user=member)
        erased = client.post("/api/v1/auth/me/erase/", {"confirmed": True}, format="json")
        self.assertEqual(erased.status_code, 200)
        member.refresh_from_db()
        member.profile.refresh_from_db()
        self.assertFalse(member.is_active)
        self.assertTrue(member.email.startswith(f"anon-{member.id}@"))
        self.assertEqual(member.profile.display_name, "Anonimizado")
        self.assertEqual(member.profile.phone, "")
        self.assertFalse(member.has_usable_password())

    def test_contact_message_dsar_requires_admin_and_exports_and_deletes_by_email(self):
        regular = self._make_user("regular@example.com", is_staff=False)
        admin = self._make_user("staff@example.com", is_staff=True)
        ContactMessage.objects.create(
            name="Visitante",
            email="lead.dsar@example.com",
            message="Consulta inicial",
            accept_terms=True,
            privacy_notice_version="2026-11-v1",
        )

        client = APIClient()
        client.force_authenticate(user=regular)
        self.assertEqual(client.get("/api/v1/contact/messages/dsar/?email=lead.dsar@example.com").status_code, 403)

        client.force_authenticate(user=admin)
        exported = client.get("/api/v1/contact/messages/dsar/?email=lead.dsar@example.com")
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.json()["data"]["count"], 1)

        deleted = client.delete("/api/v1/contact/messages/dsar/?email=lead.dsar@example.com")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["data"]["deleted"], 1)
        self.assertEqual(ContactMessage.objects.filter(email__iexact="lead.dsar@example.com").count(), 0)
