from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["event", "user", "tenant", "ip_address", "created_at"]
    search_fields = ["user__email", "tenant__name", "event", "correlation_id"]
    list_filter = ["event", "tenant"]
    readonly_fields = ["metadata", "created_at"]
