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
        response = client.post("/api/v1/tenants/onboarding/", {"name": "Acme"}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["data"]["access"] == login.data["data"]["access"])
        membership = TenantMembership.objects.get(user=user, tenant_id=response.data["data"]["tenant_id"])
        self.assertTrue(membership.membership_roles.filter(role__code="TENANT_OWNER").exists())


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
