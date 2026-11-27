"""PRV-007 & PRV-009 / QG-2: Fast JWT revocation markers and optional HttpOnly refresh cookie tests."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.views import REFRESH_COOKIE_NAME
from apps.sessions.revocation import KEY_PREFIX
from apps.tenants.services import create_owned_tenant


class _FakeRedisWriter:
    def __init__(self):
        self.written: dict[str, str] = {}

    def set(self, key: str, value: str, ex: int | None = None):
        self.written[key] = value
        return True


class Cycle2AuthSecurityTests(TestCase):
    def _create_verified_owner(self, email: str):
        user = get_user_model().objects.create_user(
            username=email,
            email=email,
            password="a-very-safe-password-123",
        )
        user.profile.email_verified_at = timezone.now()
        user.profile.save(update_fields=["email_verified_at", "updated_at"])
        tenant, _ = create_owned_tenant(user, "Cycle2 Corp")
        return user, tenant

    def test_prv007_logout_and_tenant_suspend_write_redis_revocation_markers(self):
        user, tenant = self._create_verified_owner("rev-owner@example.com")
        client = APIClient()
        login = client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "a-very-safe-password-123"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        access = login.data["data"]["access"]
        session_id = login.data["data"]["session_id"]

        fake_redis = _FakeRedisWriter()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        with patch("apps.sessions.revocation._get_redis_client", return_value=fake_redis):
            logout_res = client.post("/api/v1/auth/logout/")
            self.assertEqual(logout_res.status_code, 200)
            self.assertIn(f"{KEY_PREFIX}session:{session_id}", fake_redis.written)

            with patch("apps.tenants.views.stop_workspace"):
                suspend_res = client.post(
                    f"/api/v1/tenants/{tenant.id}/suspend/",
                    HTTP_X_TENANT_ID=str(tenant.id),
                )
            self.assertEqual(suspend_res.status_code, 200)
            self.assertIn(f"{KEY_PREFIX}tenant:{tenant.id}", fake_redis.written)

    @override_settings(AUTH_REFRESH_COOKIE_ENABLED=True, DEBUG=True)
    def test_prv009_httponly_refresh_cookie_flow_login_refresh_and_logout(self):
        user, _tenant = self._create_verified_owner("cookie-owner@example.com")
        client = APIClient()

        login = client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "a-very-safe-password-123"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn(REFRESH_COOKIE_NAME, login.cookies)
        cookie = login.cookies[REFRESH_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

        # Refresh using ONLY the HttpOnly cookie (empty JSON body).
        refresh_res = client.post("/api/v1/auth/refresh/", {}, format="json")
        self.assertEqual(refresh_res.status_code, 200)
        refresh_body = refresh_res.json()
        refresh_data = refresh_body["data"] if isinstance(refresh_body, dict) and "data" in refresh_body else refresh_body
        self.assertIn("access", refresh_data)
        self.assertIn(REFRESH_COOKIE_NAME, refresh_res.cookies)

        # Logout clears the refresh cookie.
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh_data['access']}")
        logout_res = client.post("/api/v1/auth/logout/")
        self.assertEqual(logout_res.status_code, 200)
        self.assertEqual(logout_res.cookies[REFRESH_COOKIE_NAME].value, "")
