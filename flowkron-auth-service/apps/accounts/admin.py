from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "display_name", "email_verified_at", "account_activated_at", "onboarding_completed_at", "mfa_enabled", "created_at"]
    search_fields = ["user__email", "display_name", "phone"]
