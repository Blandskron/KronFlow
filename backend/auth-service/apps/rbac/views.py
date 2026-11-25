from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import decorators, viewsets
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404

from apps.audit.models import AuditLog
from apps.audit.services import audit
from apps.shared.permissions import HasTenantPermission
from apps.shared.responses import ok
from apps.tenants.models import TenantMembership

from .models import Permission, TenantRole
from .serializers import AssignPermissionSerializer, AssignRoleSerializer, PermissionSerializer, TenantRoleSerializer
from .services import assert_delegable


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
        tenant_id = getattr(self.request, "authorized_tenant_id", None)
        return TenantRole.objects.filter(tenant_id=tenant_id).prefetch_related("permissions")

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.authorized_tenant_id)

    def perform_update(self, serializer):
        role = serializer.instance
        if role.is_system:
            raise ValidationError("System roles are immutable.")
        assert_delegable(self.request.authorized_membership, role)
        serializer.save()

    def perform_destroy(self, instance):
        if instance.is_system:
            raise ValidationError("System roles cannot be deleted; manage memberships instead.")
        assert_delegable(self.request.authorized_membership, instance)
        instance.delete()

    @decorators.action(detail=True, methods=["post"], url_path="permissions")
    def assign_permission(self, request, pk=None):
        role = self.get_object()
        if role.is_system:
            raise ValidationError("System roles are immutable.")
        serializer = AssignPermissionSerializer(data=request.data, context={"role": role})
        serializer.is_valid(raise_exception=True)
        permission = get_object_or_404(Permission, code=serializer.validated_data["permission_code"])
        assert_delegable(request.authorized_membership, role, permission.code)
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
        tenant_id = request.authorized_tenant_id
        serializer = AssignRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = get_object_or_404(TenantMembership, id=serializer.validated_data["membership_id"], tenant_id=tenant_id, status="active")
        role = get_object_or_404(TenantRole, tenant_id=tenant_id, code=serializer.validated_data["role_code"])
        assert_delegable(request.authorized_membership, role)
        serializer.context.update(membership=membership, role=role)
        serializer.save()
        audit(AuditLog.Event.ROLE_CHANGED, request=request, tenant=membership.tenant, action="membership_role_assigned")
        return ok({"assigned": True})
