from django.contrib import admin

from .models import APIKey, EmailVerificationToken, MfaDevice, MfaRecoveryCode, PasswordResetToken, ServiceAccount, SigningKey


@admin.register(SigningKey)
class SigningKeyAdmin(admin.ModelAdmin):
    list_display = ["kid", "algorithm", "status", "expires_at", "rotated_at", "created_at"]
    search_fields = ["kid"]
    list_filter = ["status", "algorithm"]


@admin.register(ServiceAccount)
class ServiceAccountAdmin(admin.ModelAdmin):
    list_display = ["name", "client_id", "status", "expires_at", "last_used_at"]
    search_fields = ["name", "client_id"]
    list_filter = ["status"]


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "prefix", "status", "expires_at", "last_used_at"]
    search_fields = ["name", "prefix", "tenant__name"]
    list_filter = ["status", "tenant"]


admin.site.register(EmailVerificationToken)
admin.site.register(PasswordResetToken)
admin.site.register(MfaDevice)
admin.site.register(MfaRecoveryCode)
