from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
import json
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.rbac.models import MembershipRole, TenantRole
from apps.tenants.models import Tenant, TenantInvitation, TenantMembership
from apps.tenants.serializers import AcceptInvitationSerializer
from apps.tenants.services import create_owned_tenant


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TenantOnboardingTests(TestCase):
    def test_verified_user_without_tenant_can_complete_onboarding(self):
        user = get_user_model().objects.create_user(username="owner@example.com", email="owner@example.com", password="a-very-safe-password-123")
        user.profile.email_verified_at = timezone.now()
        user.profile.save(update_fields=["email_verified_at", "updated_at"])
        client = APIClient()
        login = client.post("/api/v1/auth/login/", {"email": user.email, "password": "a-very-safe-password-123"}, format="json")

        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.data["data"]["onboarding_required"])

        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['data']['access']}")
        with patch("apps.tenants.views.ensure_open_workspace") as provision:
            response = client.post("/api/v1/tenants/onboarding/", {"name": "Acme"}, format="json")
        provision.assert_called_once()

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["data"]["access"] == login.data["data"]["access"])
        membership = TenantMembership.objects.get(user=user, tenant_id=response.data["data"]["tenant_id"])
        self.assertTrue(membership.membership_roles.filter(role__code="TENANT_OWNER").exists())
        self.assertIn("whatsapp.connect", response.data["data"]["permissions"])


@override_settings(BAILEYS_INTERNAL_TOKEN="synthetic-connector-test-credential", BAILEYS_SERVICE_URL="http://connector.test")
class WhatsAppDiagnosticsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(username="whatsapp-owner")
        cls.tenant, _ = create_owned_tenant(cls.owner, "WhatsApp Test")
        cls.other, _ = create_owned_tenant(cls.owner, "Other WhatsApp Test")
        cls.member = get_user_model().objects.create_user(username="member-without-whatsapp")
        TenantMembership.objects.create(
            user=cls.member, tenant=cls.tenant, status=TenantMembership.Status.ACTIVE,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner, token={"tenant_id": self.tenant.pk})
        self.path = f"/api/v1/tenants/{self.tenant.pk}/whatsapp/"

    def diagnostics(self, **fields):
        return {
            "status_changed_at": timezone.now().isoformat(),
            "retry_attempts": 0,
            "retry_limit": 5,
            "retry_exhausted": False,
            "next_action": "scan",
            **fields,
        }

    @patch("apps.tenants.views.requests.request")
    def test_proxies_allowlisted_diagnostics_and_an_unexpired_qr(self, upstream):
        now = timezone.now()
        upstream.return_value = Mock()
        upstream.return_value.json.return_value = {
            "status": "qr_pending",
            "qr": "data:image/png;base64,YWJj",
            "diagnostics": self.diagnostics(
                qr_expires_at=(now + timezone.timedelta(seconds=25)).isoformat(),
                recent_transitions=[{"status": "connecting", "changed_at": now.isoformat()}],
                private_debug="private-transport-value",
            ),
            "session_secret": "private-session-value",
        }
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response.data["data"]["qr"], "data:image/png;base64,YWJj")
        self.assertEqual(response.data["data"]["diagnostics"]["next_action"], "scan")
        self.assertEqual(response.data["data"]["diagnostics"]["recent_transitions"][0]["status"], "connecting")
        self.assertNotIn(b"private-", response.content)
        self.assertTrue(upstream.call_args.args[1].endswith(f"/tenants/{self.tenant.pk}/session"))

    @patch("apps.tenants.views.requests.request")
    def test_expired_missing_and_nonpending_qrs_are_filtered(self, upstream):
        now = timezone.now()
        snapshots = [
            {"status": "qr_pending", "diagnostics": self.diagnostics(qr_expires_at=(now - timezone.timedelta(seconds=1)).isoformat())},
            {"status": "qr_pending"},
            {"status": "connected", "diagnostics": self.diagnostics(qr_expires_at=(now + timezone.timedelta(seconds=25)).isoformat())},
        ]
        for snapshot in snapshots:
            with self.subTest(status=snapshot["status"]):
                upstream.return_value.json.return_value = snapshot | {"qr": "data:image/png;base64,YWJj"}
                response = self.client.get(self.path)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("qr", response.data["data"])

    @patch("apps.tenants.views.requests.request")
    def test_foreign_tenant_and_missing_permission_cannot_reach_connector(self, upstream):
        other = f"/api/v1/tenants/{self.other.pk}/whatsapp/"
        self.assertEqual(self.client.get(other).status_code, 404)
        self.client.force_authenticate(user=self.member, token={"tenant_id": self.tenant.pk})
        self.assertEqual(self.client.get(self.path).status_code, 403)
        upstream.assert_not_called()

    @patch("apps.tenants.views.requests.request")
    def test_malformed_upstream_data_is_reduced_to_a_generic_error(self, upstream):
        upstream.return_value.json.return_value = {"status": "private-transport-value"}
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"private-transport-value", response.content)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TenantInvitationTests(TestCase):
    def test_existing_user_must_match_invited_email(self):
        owner = get_user_model().objects.create_user(username="owner@example.com", email="owner@example.com", password="a-very-safe-password-123")
        tenant, _ = create_owned_tenant(owner, "Acme")
        other = get_user_model().objects.create_user(username="other@example.com", email="other@example.com", password="a-very-safe-password-123")
        other.profile.email_verified_at = timezone.now()
        other.profile.save(update_fields=["email_verified_at", "updated_at"])
        invitation = TenantInvitation.objects.create(
            tenant=tenant,
            email="invited@example.com",
            token_hash="",
            role_code="VIEWER",
            invited_by=owner,
            expires_at=timezone.now() + timezone.timedelta(days=1),
        )
        token = "safe-token"
        from apps.security.services import hash_token

        invitation.token_hash = hash_token(token)
        invitation.save(update_fields=["token_hash"])
        request = type("Request", (), {"user": other})()

        serializer = AcceptInvitationSerializer(data={"token": token}, context={"request": request})
        serializer.is_valid(raise_exception=True)

        with self.assertRaisesMessage(Exception, "La invitacion no corresponde"):
            serializer.save()

    def test_new_invited_user_can_activate_account_with_token(self):
        owner = get_user_model().objects.create_user(username="owner@example.com", email="owner@example.com", password="a-very-safe-password-123")
        tenant, _ = create_owned_tenant(owner, "Acme")
        token = "safe-token"
        from apps.security.services import hash_token

        TenantInvitation.objects.create(
            tenant=tenant,
            email="new@example.com",
            token_hash=hash_token(token),
            role_code="VIEWER",
            invited_by=owner,
            expires_at=timezone.now() + timezone.timedelta(days=1),
        )
        request = type("Request", (), {"user": None})()
        serializer = AcceptInvitationSerializer(data={"token": token, "password": "a-very-safe-password-123"}, context={"request": request})
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()

        self.assertEqual(membership.user.email, "new@example.com")
        self.assertIsNotNone(membership.user.profile.email_verified_at)
        self.assertTrue(membership.membership_roles.filter(role__code="VIEWER").exists())

    def test_last_owner_cannot_be_removed_or_degraded(self):
        owner = get_user_model().objects.create_user(username="owner@example.com", email="owner@example.com", password="a-very-safe-password-123")
        tenant, membership = create_owned_tenant(owner, "Acme")
        tenant.plan = Tenant.Plan.STARTER
        tenant.subscription_status = Tenant.SubscriptionStatus.ACTIVE
        tenant.save(update_fields=["plan", "subscription_status"])
        owner_role = TenantRole.objects.get(tenant=tenant, code="TENANT_OWNER")
        self.assertEqual(MembershipRole.objects.filter(membership=membership, role=owner_role).count(), 1)

        client = APIClient()
        owner.profile.email_verified_at = timezone.now()
        owner.profile.save(update_fields=["email_verified_at", "updated_at"])
        login = client.post("/api/v1/auth/login/", {"email": owner.email, "password": "a-very-safe-password-123"}, format="json")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['data']['access']}")

        delete_response = client.delete(f"/api/v1/tenants/{tenant.id}/members/{membership.id}/", HTTP_X_TENANT_ID=str(tenant.id))
        self.assertEqual(delete_response.status_code, 400)

        patch_response = client.patch(
            f"/api/v1/tenants/{tenant.id}/members/{membership.id}/",
            {"role_codes": ["VIEWER"]},
            format="json",
            HTTP_X_TENANT_ID=str(tenant.id),
        )
        self.assertEqual(patch_response.status_code, 400)
        patch_body = getattr(patch_response, "data", None) or json.loads(patch_response.content)
        self.assertIn("LAST_OWNER_ROLE_CHANGE_DENIED", str(patch_body))


class TenantPrivacyProfileTests(TestCase):
    def test_only_owner_or_admin_can_update_privacy_profile_and_public_endpoint_exposes_it(self):
        owner = get_user_model().objects.create_user(
            username="privacy-owner@example.com",
            email="privacy-owner@example.com",
            password="a-very-safe-password-123",
        )
        viewer = get_user_model().objects.create_user(
            username="privacy-viewer@example.com",
            email="privacy-viewer@example.com",
            password="a-very-safe-password-123",
        )
        tenant, _ = create_owned_tenant(owner, "Privacy Corp")
        viewer_membership = TenantMembership.objects.create(
            user=viewer, tenant=tenant, status=TenantMembership.Status.ACTIVE,
        )
        viewer_role = TenantRole.objects.get(tenant=tenant, code="VIEWER")
        MembershipRole.objects.create(membership=viewer_membership, role=viewer_role)

        client = APIClient()
        client.force_authenticate(user=viewer, token={"tenant_id": tenant.pk})
        forbidden = client.patch(
            f"/api/v1/tenants/{tenant.pk}/",
            {
                "privacy_jurisdiction": "EU",
                "dpo_contact_email": "dpo@privacycorp.test",
                "privacy_policy_url": "https://privacycorp.test/privacy",
            },
            format="json",
            HTTP_X_TENANT_ID=str(tenant.pk),
        )
        self.assertEqual(forbidden.status_code, 403)

        client.force_authenticate(user=owner, token={"tenant_id": tenant.pk})
        updated = client.patch(
            f"/api/v1/tenants/{tenant.pk}/",
            {
                "privacy_jurisdiction": "EU",
                "dpo_contact_email": "dpo@privacycorp.test",
                "privacy_policy_url": "https://privacycorp.test/privacy",
            },
            format="json",
            HTTP_X_TENANT_ID=str(tenant.pk),
        )
        self.assertEqual(updated.status_code, 200)
        updated_body = updated.json()
        updated_payload = updated_body["data"] if isinstance(updated_body, dict) and "data" in updated_body else updated_body
        self.assertEqual(updated_payload["privacy_jurisdiction"], "EU")
        self.assertEqual(updated_payload["dpo_contact_email"], "dpo@privacycorp.test")
        self.assertEqual(updated_payload["privacy_policy_url"], "https://privacycorp.test/privacy")

        public_client = APIClient()
        public_res = public_client.get(f"/api/v1/tenants/privacy-profile/{tenant.slug}/")
        self.assertEqual(public_res.status_code, 200)
        public_data = public_res.json()["data"]
        self.assertEqual(public_data["privacy_jurisdiction"], "EU")
        self.assertEqual(public_data["dpo_contact_email"], "dpo@privacycorp.test")
        self.assertEqual(public_data["privacy_policy_url"], "https://privacycorp.test/privacy")
        self.assertNotIn("tax_id", public_data)
