from django.contrib import admin

from .models import UserSession


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "status", "ip_address", "expires_at", "created_at"]
    search_fields = ["user__email", "tenant__name", "ip_address"]
    list_filter = ["status", "tenant"]
