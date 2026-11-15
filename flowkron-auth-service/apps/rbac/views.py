from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import decorators, viewsets

from apps.audit.models import AuditLog
from apps.audit.services import audit
from apps.shared.permissions import HasTenantPermission
from apps.shared.responses import ok
from apps.tenants.models import TenantMembership

from .models import Permission, TenantRole
from .serializers import AssignPermissionSerializer, AssignRoleSerializer, PermissionSerializer, TenantRoleSerializer


@extend_schema_view(
    list=extend_schema(tags=["RBAC - Permissions"]),
    retrieve=extend_schema(tags=["RBAC - Permissions"]),
)
class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Permission.objects.all().order_by("resource", "action")
    serializer_class = PermissionSerializer


@extend_schema_view(
    list=extend_schema(tags=["RBAC - Roles"]),
    retrieve=extend_schema(tags=["RBAC - Roles"]),
    create=extend_schema(tags=["RBAC - Roles"]),
    update=extend_schema(tags=["RBAC - Roles"]),
    partial_update=extend_schema(tags=["RBAC - Roles"]),
    destroy=extend_schema(tags=["RBAC - Roles"]),
    assign_permission=extend_schema(tags=["RBAC - Role Permissions"]),
)
class TenantRoleViewSet(viewsets.ModelViewSet):
    serializer_class = TenantRoleSerializer
    permission_classes = [HasTenantPermission]
    required_permission = "roles.assign"

    def get_queryset(self):
        tenant_id = self.request.headers.get("X-Tenant-ID") or self.request.query_params.get("tenant_id") or (self.request.auth.get("tenant_id") if self.request.auth else None)
        return TenantRole.objects.filter(tenant_id=tenant_id).prefetch_related("permissions")

    @decorators.action(detail=True, methods=["post"], url_path="permissions")
    def assign_permission(self, request, pk=None):
        role = self.get_object()
        serializer = AssignPermissionSerializer(data=request.data, context={"role": role})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(AuditLog.Event.ROLE_CHANGED, request=request, tenant=role.tenant, role=role.code, action="permission_assigned")
        return ok(TenantRoleSerializer(role).data)


@extend_schema_view(
    assign=extend_schema(tags=["RBAC - Membership Roles"]),
)
class MembershipRoleViewSet(viewsets.ViewSet):
    serializer_class = AssignRoleSerializer
    permission_classes = [HasTenantPermission]
    required_permission = "roles.assign"

    @decorators.action(detail=False, methods=["post"], url_path="assign")
    def assign(self, request):
        tenant_id = request.headers.get("X-Tenant-ID") or request.data.get("tenant_id") or (request.auth.get("tenant_id") if request.auth else None)
        membership = TenantMembership.objects.get(id=request.data["membership_id"], tenant_id=tenant_id)
        serializer = AssignRoleSerializer(data=request.data, context={"membership": membership})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(AuditLog.Event.ROLE_CHANGED, request=request, tenant=membership.tenant, action="membership_role_assigned")
        return ok({"assigned": True})
