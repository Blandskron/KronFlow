from django.contrib import admin

from .models import MembershipRole, Permission, RolePermission, TenantRole


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ["code", "resource", "action"]
    search_fields = ["code", "resource", "action"]


@admin.register(TenantRole)
class TenantRoleAdmin(admin.ModelAdmin):
    list_display = ["tenant", "code", "name", "is_system"]
    search_fields = ["tenant__name", "code", "name"]
    list_filter = ["is_system"]


admin.site.register(RolePermission)
admin.site.register(MembershipRole)
