from rest_framework import serializers

from .models import MembershipRole, Permission, RolePermission, TenantRole


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "code", "resource", "action", "description"]


class TenantRoleSerializer(serializers.ModelSerializer):
    permission_codes = serializers.SlugRelatedField(source="permissions", slug_field="code", many=True, read_only=True)

    class Meta:
        model = TenantRole
        fields = ["id", "tenant", "code", "name", "description", "is_system", "permission_codes", "created_at", "updated_at"]
        read_only_fields = ["is_system", "created_at", "updated_at"]


class AssignPermissionSerializer(serializers.Serializer):
    permission_code = serializers.CharField()

    def save(self, **kwargs):
        role = self.context["role"]
        permission = Permission.objects.get(code=self.validated_data["permission_code"])
        return RolePermission.objects.get_or_create(role=role, permission=permission)[0]


class AssignRoleSerializer(serializers.Serializer):
    role_code = serializers.CharField()

    def save(self, **kwargs):
        membership = self.context["membership"]
        role = TenantRole.objects.get(tenant=membership.tenant, code=self.validated_data["role_code"])
        return MembershipRole.objects.get_or_create(membership=membership, role=role)[0]
