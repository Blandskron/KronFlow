from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone


class UserProfileSignalTests(TestCase):
    def test_profile_is_created_for_native_auth_user(self):
        user = get_user_model().objects.create_user(username="u@example.com", email="u@example.com", password="a-very-safe-password-123")
        user.profile.email_verified_at = timezone.now()
        user.profile.save()

        self.assertEqual(user.profile.user, user)
