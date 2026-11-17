import hashlib
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.rbac.models import MembershipRole, TenantRole
from apps.tenants.models import Tenant, TenantInvitation, TenantMembership, TenantOperationalRuntime
from apps.tenants.services import create_owned_tenant, provision_operational_runtime, stop_workspace


class AuthorizationBoundaryTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.owner = users.objects.create_user(username="owner@example.com")
        self.other = users.objects.create_user(username="other@example.com")
        self.tenant, self.membership = create_owned_tenant(self.owner, "Workspace A")
        self.target, self.target_member = create_owned_tenant(self.other, "Workspace B")
        self.client = APIClient()
        self.client.force_authenticate(self.owner, {"tenant_id": str(self.tenant.pk), "amr": "mfa"})

    def become_admin(self):
        self.membership.membership_roles.all().delete()
        MembershipRole.objects.create(membership=self.membership, role=self.tenant.roles.get(code="TENANT_ADMIN"))

    def test_conflicting_query_and_body_cannot_assign_another_workspace(self):
        response = self.client.post(
            f"/api/v1/rbac/membership-roles/assign/?tenant_id={self.tenant.pk}",
            {"tenant_id": self.target.pk, "membership_id": self.target_member.pk, "role_code": "VIEWER"}, format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.target_member.membership_roles.filter(role__code="VIEWER").exists())

    def test_cross_workspace_role_creation_and_move_are_denied(self):
        response = self.client.post("/api/v1/rbac/roles/", {"tenant": self.target.pk, "code": "CUSTOM", "name": "Custom"}, format="json")
        self.assertEqual(response.status_code, 403)
        role = self.tenant.roles.create(code="CUSTOM", name="Custom")
        response = self.client.patch(f"/api/v1/rbac/roles/{role.pk}/", {"tenant": self.target.pk}, format="json")
        self.assertEqual(response.status_code, 403)
        role.refresh_from_db()
        self.assertEqual(role.tenant_id, self.tenant.pk)

    def test_custom_role_creation_and_delegation_still_work(self):
        response = self.client.post("/api/v1/rbac/roles/", {"code": "CUSTOM", "name": "Custom"}, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        role = self.tenant.roles.get(code="CUSTOM")
        response = self.client.post(f"/api/v1/rbac/roles/{role.pk}/permissions/", {"permission_code": "users.read"}, format="json")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/v1/rbac/membership-roles/assign/", {"membership_id": self.membership.pk, "role_code": "CUSTOM"}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_system_role_cannot_be_renamed_deleted_or_modified(self):
        role = self.tenant.roles.get(code="TENANT_OWNER")
        self.assertEqual(self.client.patch(f"/api/v1/rbac/roles/{role.pk}/", {"code": "OTHER"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/v1/rbac/roles/{role.pk}/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/v1/rbac/roles/{role.pk}/permissions/", {"permission_code": "users.read"}, format="json").status_code, 400)

    def test_admin_cannot_promote_self_by_assignment_update_or_invitation(self):
        self.become_admin()
        response = self.client.post("/api/v1/rbac/membership-roles/assign/", {"membership_id": self.membership.pk, "role_code": "TENANT_OWNER"}, format="json")
        self.assertEqual(response.status_code, 403)
        response = self.client.patch(f"/api/v1/tenants/{self.tenant.pk}/members/{self.membership.pk}/", {"role_codes": ["TENANT_OWNER"]}, format="json")
        self.assertEqual(response.status_code, 403)
        response = self.client.post(f"/api/v1/tenants/{self.tenant.pk}/invite/", {"email": "invited@example.com", "role_code": "TENANT_OWNER"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_grant_higher_permission_to_custom_role(self):
        role = self.tenant.roles.create(code="CUSTOM", name="Custom")
        self.become_admin()
        response = self.client.post(f"/api/v1/rbac/roles/{role.pk}/permissions/", {"permission_code": "tenants.manage"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(role.permissions.exists())

    def test_last_owner_status_cannot_be_revoked_or_suspended(self):
        for status in ("revoked", "suspended"):
            response = self.client.patch(f"/api/v1/tenants/{self.tenant.pk}/members/{self.membership.pk}/", {"status": status}, format="json")
            self.assertEqual(response.status_code, 400)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, "active")

    def test_viewer_invitation_does_not_restore_revoked_owner_permissions(self):
        self.other.email = "other@example.com"
        self.other.save(update_fields=["email"])
        self.other.profile.email_verified_at = timezone.now()
        self.other.profile.save(update_fields=["email_verified_at"])
        former = TenantMembership.objects.create(user=self.other, tenant=self.tenant, status="revoked")
        MembershipRole.objects.create(membership=former, role=self.tenant.roles.get(code="TENANT_OWNER"))
        invitation_token = "synthetic-invitation"
        TenantInvitation.objects.create(tenant=self.tenant, email=self.other.email, token_hash=hashlib.sha256(invitation_token.encode()).hexdigest(), role_code="VIEWER", invited_by=self.owner, expires_at=timezone.now() + timezone.timedelta(days=1))
        self.client.force_authenticate(self.other)
        response = self.client.post("/api/v1/tenants/invitations/accept/", {"token": invitation_token}, format="json")
        self.assertEqual(response.status_code, 200, response.json())
        former.refresh_from_db()
        self.assertEqual(former.status, "active")
        self.assertEqual(list(former.membership_roles.values_list("role__code", flat=True)), ["VIEWER"])

    def test_api_key_conflicting_tenant_selectors_are_denied(self):
        response = self.client.post(f"/api/v1/security/api-keys/?tenant_id={self.tenant.pk}", {"tenant_id": self.target.pk, "name": "Test", "scopes": []}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_audit_without_tenant_header_never_lists_global_or_other_workspace_events(self):
        AuditLog.objects.create(event=AuditLog.Event.LOGIN_FAILED, metadata={"scope": "global"})
        AuditLog.objects.create(tenant=self.target, event=AuditLog.Event.LOGIN_FAILED, metadata={"scope": "other"})
        own = AuditLog.objects.create(tenant=self.tenant, event=AuditLog.Event.ROLE_CHANGED)
        response = self.client.get("/api/v1/audit/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        records = payload if isinstance(payload, list) else payload.get("results", payload.get("data"))
        self.assertEqual([row["id"] for row in records], [own.pk])

    def test_status_cannot_bypass_lifecycle_actions(self):
        response = self.client.patch(f"/api/v1/tenants/{self.tenant.pk}/", {"status": "archived"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status, "active")

    @patch("apps.tenants.views.stop_workspace")
    def test_suspend_and_delete_stop_channel_first(self, stop):
        response = self.client.post(f"/api/v1/tenants/{self.tenant.pk}/suspend/")
        self.assertEqual(response.status_code, 200)
        stop.assert_called_once()
        stop.reset_mock()
        response = self.client.delete(f"/api/v1/tenants/{self.tenant.pk}/")
        self.assertEqual(response.status_code, 204)
        stop.assert_called_once()

    @patch("apps.tenants.views.stop_workspace", side_effect=requests.RequestException("unavailable"))
    def test_failed_channel_stop_prevents_delete(self, stop):
        response = self.client.delete(f"/api/v1/tenants/{self.tenant.pk}/")
        self.assertEqual(response.status_code, 500)
        self.assertTrue(Tenant.objects.filter(pk=self.tenant.pk).exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_suspended_workspace_cannot_be_reprovisioned(self):
        self.tenant.status = "suspended"
        self.tenant.save()
        with patch("apps.tenants.services.requests.post") as post:
            with self.assertRaises(requests.RequestException):
                provision_operational_runtime(self.tenant)
        post.assert_not_called()

    def test_provision_timeout_keeps_projection_and_suspension_still_checks_operational(self):
        suspended = Mock(status_code=200)
        suspended.json.return_value = {"status": "suspended"}
        with patch("apps.tenants.services.requests.post", side_effect=[requests.ReadTimeout("synthetic timeout"), suspended]) as post:
            with self.assertRaises(requests.ReadTimeout):
                provision_operational_runtime(self.tenant)
            self.assertEqual(TenantOperationalRuntime.objects.get(tenant=self.tenant).status, "provision_failed")
            stop_workspace(self.tenant)
            self.assertTrue(post.call_args.args[0].endswith(f"/{self.tenant.pk}/suspend"))
        self.assertEqual(TenantOperationalRuntime.objects.get(tenant=self.tenant).status, "suspended")
