from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.sessions.models import UserSession
from apps.tenants.models import Tenant, TenantMembership


class UserSessionTests(TestCase):
    def test_create_from_request_records_device_context(self):
        user = get_user_model().objects.create_user(username="u@example.com", email="u@example.com")
        tenant = Tenant.objects.create(name="Acme", legal_name="Acme")
        membership = TenantMembership.objects.create(user=user, tenant=tenant, status="active")
        request = RequestFactory().get("/", HTTP_USER_AGENT="pytest-agent", REMOTE_ADDR="127.0.0.1")

        session = UserSession.objects.create_from_request(user=user, membership=membership, request=request)

        self.assertEqual(session.user, user)
        self.assertEqual(session.tenant, tenant)
        self.assertEqual(session.user_agent, "pytest-agent")
        self.assertTrue(session.is_active)
