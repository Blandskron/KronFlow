from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="profile", on_delete=models.CASCADE)
    display_name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    avatar_url = models.URLField(blank=True)
    timezone = models.CharField(max_length=64, default="America/Santiago")
    locale = models.CharField(max_length=16, default="es-CL")
    email_verified_at = models.DateTimeField(null=True, blank=True)
    account_activated_at = models.DateTimeField(null=True, blank=True)
    initial_password_set_at = models.DateTimeField(null=True, blank=True)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)
    mfa_enabled = models.BooleanField(default=False)
    mfa_confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "iam_user_profile"

    def __str__(self):
        return self.display_name or self.user.get_username()
