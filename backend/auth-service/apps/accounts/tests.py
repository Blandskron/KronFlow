import secrets
import os
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from apps.audit.models import AuditLog
from apps.sessions.models import UserSession
from apps.tenants.models import Tenant, TenantMembership


class UserProfileSignalTests(TestCase):
    def test_profile_is_created_for_native_auth_user(self):
        user = get_user_model().objects.create_user(username="u@example.com", email="u@example.com", password="a-very-safe-password-123")
        user.profile.email_verified_at = timezone.now()
        user.profile.save()

        self.assertEqual(user.profile.user, user)


@override_settings(DEBUG=True, IAM_PLATFORM_TENANT_SLUG="flowkron-platform")
class BootstrapSuperuserTests(TestCase):
    def test_custom_initial_admin_is_verified_owner_and_keeps_their_password(self):
        email, username, password = "admin-test@example.com", "local-admin", secrets.token_urlsafe(24)
        config = {
            "DJANGO_SUPERUSER_EMAIL": email,
            "DJANGO_SUPERUSER_USERNAME": username,
            "DJANGO_SUPERUSER_PASSWORD": password,
            "FLOWKRON_BIND_HOST": "127.0.0.1",
        }
        with patch.dict(os.environ, config), patch(
            "apps.accounts.management.commands.bootstrap_local_workspace.provision_operational_runtime"
        ) as provision, self.captureOnCommitCallbacks(execute=True) as callbacks:
            call_command("bootstrap_local_workspace", explicit=True, verbosity=0)

        self.assertFalse(callbacks, "Bootstrap must not send verification emails.")
        user = get_user_model().objects.get(username=username)
        self.assertTrue(user.is_active and user.is_staff and user.is_superuser)
        self.assertIsNotNone(user.profile.email_verified_at)
        self.assertIsNotNone(user.profile.account_activated_at)
        membership = user.memberships.select_related("tenant").get(status=TenantMembership.Status.ACTIVE)
        self.assertEqual(membership.tenant.name, "BLANDSKRON")
        self.assertEqual(membership.tenant.plan, Tenant.Plan.STARTER)
        self.assertTrue(membership.membership_roles.filter(role__code="TENANT_OWNER").exists())
        provision.assert_called_once_with(membership.tenant)

        response = self.client.post(reverse("auth-login"), {"email": email, "password": password}, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        with patch.dict(os.environ, {**config, "DJANGO_SUPERUSER_PASSWORD": secrets.token_urlsafe(24)}), patch(
            "apps.accounts.management.commands.bootstrap_local_workspace.provision_operational_runtime"
        ):
            call_command("bootstrap_local_workspace", explicit=True, verbosity=0)
        user.refresh_from_db()
        self.assertTrue(user.check_password(password))
        self.assertEqual(user.memberships.count(), 1)

    def test_bootstrap_does_not_promote_an_existing_regular_user(self):
        user = get_user_model().objects.create_user(username="regular", email="regular@example.com")
        with self.assertRaises(CommandError):
            call_command("ensure_superuser", email=user.email, username=user.username, password=secrets.token_urlsafe(24), create_only=True)
        user.refresh_from_db()
        self.assertFalse(user.is_staff or user.is_superuser)


@override_settings(
    AUTH_SELF_SIGNUP_ENABLED=True,
    GOOGLE_OAUTH_CLIENT_ID="example.apps.googleusercontent.com",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "public-auth-tests"}},
)
class PublicAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_email_signup_verification_and_logout(self):
        email, password = "demo@example.com", secrets.token_urlsafe(24)
        response = self.client.post(reverse("auth-signup"), {"email": email}, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertFalse(get_user_model().objects.filter(email=email).exists())
        url = next(line for line in mail.outbox[0].body.splitlines() if line.startswith("http"))
        token = parse_qs(urlsplit(url).fragment)["token"][0]
        payload = {"token": token, "password": password}
        self.assertEqual(self.client.post(reverse("auth-signup-complete"), payload, format="json").status_code, 201)
        self.assertEqual(self.client.post(reverse("auth-signup-complete"), payload, format="json").status_code, 409)

        response = self.client.post(reverse("auth-login"), {"email": email, "password": password}, format="json")
        self.assertEqual(response.status_code, 200)
        session = response.data["data"]
        self.assertTrue(session["onboarding_required"])
        refreshed = self.client.post(reverse("auth-refresh"), {"refresh": session["refresh"]}, format="json")
        self.assertEqual(refreshed.status_code, 200)
        tokens = refreshed.json()["data"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.post(reverse("auth-logout"), {}, format="json").status_code, 200)
        self.client.credentials()
        denied = self.client.post(reverse("auth-refresh"), {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(denied.status_code, 401)

    def test_google_checks_signature_audience_nonce_replay_and_mfa(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        nonce = self.client.get(reverse("auth-options")).data["data"]["google_nonce"]
        now = timezone.now()
        claims = {
            "iss": "https://accounts.google.com", "aud": "example.apps.googleusercontent.com",
            "iat": now, "exp": now + timezone.timedelta(minutes=5), "sub": "test-identity",
            "email": "synthetic@gmail.com", "email_verified": True, "nonce": nonce,
        }

        def login(nonce, **overrides):
            token = jwt.encode({**claims, **overrides}, key, algorithm="RS256", headers={"kid": "test"})
            return self.client.post(reverse("auth-google"), {"nonce": nonce, "credential": token}, format="json")

        with patch("apps.accounts.public_auth.GOOGLE_KEYS.get_signing_key_from_jwt", return_value=SimpleNamespace(key=key.public_key())):
            self.assertEqual(login(nonce, aud="different-client").status_code, 400)
            self.assertEqual(login("invalid").status_code, 400)
            self.assertEqual(login(nonce, email="synthetic@example.com").status_code, 403)
            self.assertEqual(login(nonce).status_code, 200)
            self.assertEqual(login(nonce).status_code, 400)
            profile = get_user_model().objects.get(email="synthetic@gmail.com").profile
            self.assertEqual(profile.google_subject, "test-identity")
            self.assertFalse(profile.user.has_usable_password())
            profile.mfa_enabled = True
            profile.save(update_fields=["mfa_enabled"])
            fresh_nonce = self.client.get(reverse("auth-options")).data["data"]["google_nonce"]
            claims["nonce"] = fresh_nonce
            self.assertTrue(login(fresh_nonce).data["error_code"].endswith("_MFA_REQUIRED"))

    def test_google_does_not_link_existing_password_account_by_email(self):
        existing = get_user_model().objects.create_user(username="existing@gmail.com", email="existing@gmail.com")
        with patch("apps.accounts.public_auth.verify_google_credential", return_value={
            "sub": "independent-subject", "email": existing.email, "email_verified": True,
        }):
            response = self.client.post(reverse("auth-google"), {"credential": "test-token", "nonce": "test-nonce"}, format="json")
        self.assertEqual(response.status_code, 409)
        existing.profile.refresh_from_db()
        self.assertIsNone(existing.profile.google_subject)

    def test_refresh_token_reuse_marks_session_compromised_and_blocks_subsequent_refresh(self):
        password = secrets.token_urlsafe(24)
        user = get_user_model().objects.create_user(username="reuse@example.com", email="reuse@example.com", password=password)
        user.profile.email_verified_at = timezone.now()
        user.profile.save(update_fields=["email_verified_at"])

        login_res = self.client.post(reverse("auth-login"), {"email": user.email, "password": password}, format="json")
        self.assertEqual(login_res.status_code, 200)
        session_id = login_res.data["data"]["session_id"]
        refresh_1 = login_res.data["data"]["refresh"]

        first_refresh = self.client.post(reverse("auth-refresh"), {"refresh": refresh_1}, format="json")
        self.assertEqual(first_refresh.status_code, 200)
        refresh_2 = first_refresh.json()["data"]["refresh"]

        # Replaying rotated/blacklisted refresh_1 must return 401 and compromise the session.
        replay = self.client.post(reverse("auth-refresh"), {"refresh": refresh_1}, format="json")
        self.assertEqual(replay.status_code, 401)

        session = UserSession.objects.get(id=session_id)
        self.assertEqual(session.status, UserSession.Status.COMPROMISED)
        self.assertIn("REFRESH_REUSE_DETECTED", session.risk_flags)
        self.assertEqual(session.risk_score, 100)
        self.assertTrue(
            AuditLog.objects.filter(user=user, event=AuditLog.Event.SESSION_COMPROMISED).exists()
        )

        # Subsequent refresh with refresh_2 must now fail because the session is compromised.
        blocked = self.client.post(reverse("auth-refresh"), {"refresh": refresh_2}, format="json")
        self.assertEqual(blocked.status_code, 401)
