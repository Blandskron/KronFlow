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
        read_only_fields = ["tenant", "is_system", "created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context["request"]
        supplied = self.initial_data.get("tenant")
        if supplied is not None and str(supplied) != str(request.authorized_tenant_id):
            raise serializers.ValidationError({"tenant": "Tenant does not match the authorized workspace."})
        code = attrs.get("code")
        if code is not None:
            from .services import BASE_ROLES
            if code in BASE_ROLES and (not self.instance or self.instance.code != code):
                raise serializers.ValidationError({"code": "Reserved system role."})
            taken = TenantRole.objects.filter(tenant_id=request.authorized_tenant_id, code=code)
            if self.instance:
                taken = taken.exclude(pk=self.instance.pk)
            if taken.exists():
                raise serializers.ValidationError({"code": "Role code already exists in this workspace."})
        return attrs


class AssignPermissionSerializer(serializers.Serializer):
    permission_code = serializers.CharField()

    def save(self, **kwargs):
        role = self.context["role"]
        permission = Permission.objects.get(code=self.validated_data["permission_code"])
        return RolePermission.objects.get_or_create(role=role, permission=permission)[0]


class AssignRoleSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField(min_value=1)
    role_code = serializers.CharField()

    def save(self, **kwargs):
        membership = self.context["membership"]
        role = self.context["role"]
        return MembershipRole.objects.get_or_create(membership=membership, role=role)[0]
