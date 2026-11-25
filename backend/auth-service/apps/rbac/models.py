from django.db import models


class Permission(models.Model):
    code = models.CharField(max_length=96, unique=True)
    resource = models.CharField(max_length=64)
    action = models.CharField(max_length=64)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iam_permission"
        indexes = [models.Index(fields=["resource", "action"], name="iam_permiss_resourc_7b7b23_idx")]

    def __str__(self):
        return self.code


class TenantRole(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", related_name="roles", on_delete=models.CASCADE)
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=255, blank=True)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, through="RolePermission", related_name="tenant_roles")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "iam_tenant_role"
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="uniq_tenant_role_code")]

    def __str__(self):
        return f"{self.tenant_id}:{self.code}"


class RolePermission(models.Model):
    role = models.ForeignKey(TenantRole, related_name="role_permissions", on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, related_name="role_permissions", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iam_role_permission"
        constraints = [models.UniqueConstraint(fields=["role", "permission"], name="uniq_role_permission")]


class MembershipRole(models.Model):
    membership = models.ForeignKey("tenants.TenantMembership", related_name="membership_roles", on_delete=models.CASCADE)
    role = models.ForeignKey(TenantRole, related_name="membership_roles", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iam_membership_role"
        constraints = [models.UniqueConstraint(fields=["membership", "role"], name="uniq_membership_role")]
