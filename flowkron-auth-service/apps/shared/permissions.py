from rest_framework import permissions


class IsEmailVerified(permissions.BasePermission):
    message = "Email no verificado."

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        return bool(request.user and request.user.is_authenticated and profile and profile.email_verified_at)


class IsMfaVerified(permissions.BasePermission):
    message = "MFA requerido."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        profile = getattr(request.user, "profile", None)
        if not profile or not profile.mfa_enabled:
            return True
        return request.auth and request.auth.get("amr") == "mfa"


class IsTenantMember(permissions.BasePermission):
    message = "No pertenece al tenant."

    def has_permission(self, request, view):
        tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
        if not tenant_id:
            return False
        return request.user.memberships.filter(tenant_id=tenant_id, status="active").exists()


class HasTenantPermission(permissions.BasePermission):
    message = "Permiso tenant requerido."

    def has_permission(self, request, view):
        required = getattr(view, "required_permission", None)
        if not required:
            return True
        if not request.user or not request.user.is_authenticated:
            return False

        query_params = getattr(request, "query_params", {})
        requested_tenant_id = request.headers.get("X-Tenant-ID") or query_params.get("tenant_id")
        if not requested_tenant_id and hasattr(request, "data"):
            requested_tenant_id = request.data.get("tenant_id")
        token_tenant_id = str(request.auth.get("tenant_id")) if request.auth and request.auth.get("tenant_id") else None
        tenant_id = str(requested_tenant_id or token_tenant_id or "")
        if not tenant_id:
            return False
        if token_tenant_id and tenant_id != token_tenant_id:
            return False
        membership = request.user.memberships.filter(tenant_id=tenant_id, status="active").select_related("tenant").first()
        if not membership:
            return False

        from apps.rbac.services import permissions_for_membership

        return required in permissions_for_membership(membership)


class IsTenantAdmin(HasTenantPermission):
    def has_permission(self, request, view):
        roles = request.auth.get("roles", []) if request.auth else []
        return "TENANT_OWNER" in roles or "TENANT_ADMIN" in roles


class RequiresMfaForCriticalAction(permissions.BasePermission):
    message = "MFA requerido para esta accion critica."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if not request.auth:
            return False
        return request.auth.get("amr") == "mfa"


class IsPlatformAdminWithMfa(RequiresMfaForCriticalAction):
    message = "Superuser con MFA requerido para esta accion de plataforma."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
            and super().has_permission(request, view)
        )
