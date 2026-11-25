import jwt
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from rest_framework.test import APIRequestFactory

from apps.shared.permissions import HasTenantPermission, RequiresMfaForCriticalAction
from apps.security.models import APIKey, ServiceAccount, SigningKey
from apps.security.services import (
    create_api_key,
    create_service_account,
    introspect_token,
    issue_client_credentials_token,
    jwks_payload,
    rotate_api_key,
    rotate_signing_key,
)
from apps.tenants.models import Tenant


class SigningKeyTests(TestCase):
    def test_rotation_keeps_previous_key_inactive_for_jwks_compatibility(self):
        first = rotate_signing_key()
        second = rotate_signing_key()

        first.refresh_from_db()
        kids = {item["kid"] for item in jwks_payload()["keys"]}

        self.assertEqual(first.status, SigningKey.Status.INACTIVE)
        self.assertEqual(second.status, SigningKey.Status.ACTIVE)
        self.assertIn(first.kid, kids)
        self.assertIn(second.kid, kids)


class ServiceAccountTests(TestCase):
    def test_client_credentials_issues_introspectable_scoped_token(self):
        account = create_service_account("rag-service", scopes=["auth.verify_token", "users.read"])

        token = issue_client_credentials_token(account.client_id, account.plain_client_secret, ["users.read"])
        claims = jwt.decode(token, options={"verify_signature": False})
        result = introspect_token(token)

        self.assertEqual(claims["typ"], "service_account")
        self.assertEqual(claims["scopes"], ["users.read"])
        self.assertTrue(result["active"])
        self.assertIsNotNone(ServiceAccount.objects.get(id=account.id).last_used_at)

    def test_introspection_requires_service_account_scope(self):
        from apps.security.views import TokenIntrospectionView

        request = APIRequestFactory().post("/api/v1/auth/introspect/", {"token": "x"}, format="json", REMOTE_ADDR="127.0.0.92")
        response = TokenIntrospectionView.as_view()(request)

        self.assertEqual(response.status_code, 401)


class APIKeyTests(TestCase):
    def test_api_key_is_hashed_and_rotation_revokes_old_key(self):
        user = get_user_model().objects.create_user(username="owner@example.com", email="owner@example.com")
        tenant = Tenant.objects.create(name="Acme", legal_name="Acme")

        api_key = create_api_key(tenant, "Zapier", ["users.read"], created_by=user)
        plain = api_key.plain_key
        replacement = rotate_api_key(api_key)

        api_key.refresh_from_db()
        self.assertNotEqual(api_key.key_hash, plain)
        self.assertEqual(api_key.status, APIKey.Status.REVOKED)
        self.assertEqual(replacement.status, APIKey.Status.ACTIVE)
        self.assertNotEqual(replacement.key_hash, api_key.key_hash)


class SessionRiskTests(TestCase):
    def test_new_session_gets_risk_flag(self):
        from apps.sessions.models import UserSession
        from apps.sessions.services import evaluate_session_risk
        from apps.tenants.models import TenantMembership

        user = get_user_model().objects.create_user(username="u@example.com", email="u@example.com")
        tenant = Tenant.objects.create(name="Acme", legal_name="Acme")
        membership = TenantMembership.objects.create(user=user, tenant=tenant, status="active")
        request = RequestFactory().get("/", HTTP_USER_AGENT="pytest-agent", REMOTE_ADDR="127.0.0.1")
        session = UserSession.objects.create_from_request(user=user, membership=membership, request=request)

        flags = evaluate_session_risk(session, request)

        self.assertIn("NEW_DEVICE", flags)
        self.assertGreater(session.risk_score, 0)


class PermissionHardeningTests(TestCase):
    def test_tenant_permission_requires_matching_token_tenant_and_membership(self):
        from apps.tenants.models import TenantMembership

        user = get_user_model().objects.create_user(username="u@example.com", email="u@example.com")
        tenant = Tenant.objects.create(name="Acme", legal_name="Acme", plan=Tenant.Plan.STARTER, subscription_status=Tenant.SubscriptionStatus.ACTIVE)
        TenantMembership.objects.create(user=user, tenant=tenant, status="active")
        request = APIRequestFactory().get("/", HTTP_X_TENANT_ID=str(tenant.id + 1))
        request.user = user
        request.auth = {"tenant_id": str(tenant.id), "permissions": ["api_keys.manage"]}
        request.query_params = {}
        request.data = {}
        view = type("View", (), {"required_permission": "api_keys.manage"})()

        self.assertFalse(HasTenantPermission().has_permission(request, view))

    def test_tenant_permission_uses_current_workspace_status(self):
        from apps.rbac.models import MembershipRole, TenantRole
        from apps.rbac.services import seed_roles_for_tenant
        from apps.tenants.models import TenantMembership

        user = get_user_model().objects.create_user(username="u@example.com", email="u@example.com")
        tenant = Tenant.objects.create(name="Free Co", legal_name="Free Co")
        membership = TenantMembership.objects.create(user=user, tenant=tenant, status="active")
        seed_roles_for_tenant(tenant)
        MembershipRole.objects.create(membership=membership, role=TenantRole.objects.get(tenant=tenant, code="TENANT_OWNER"))
        request = APIRequestFactory().post("/", {"tenant_id": tenant.id}, format="json")
        request.user = user
        request.auth = {"tenant_id": str(tenant.id), "permissions": ["members.manage"]}
        view = type("View", (), {"required_permission": "members.manage"})()

        self.assertTrue(HasTenantPermission().has_permission(request, view))

        tenant.status = Tenant.Status.SUSPENDED
        tenant.save(update_fields=["status"])
        self.assertFalse(HasTenantPermission().has_permission(request, view))

    def test_critical_action_requires_mfa_claim(self):
        user = get_user_model().objects.create_user(username="u@example.com", email="u@example.com")
        request = APIRequestFactory().post("/")
        request.user = user
        request.auth = {"amr": "pwd"}

        self.assertFalse(RequiresMfaForCriticalAction().has_permission(request, None))
