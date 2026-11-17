BASE_PERMISSIONS = [
    "users.read",
    "users.create",
    "roles.assign",
    "agents.create",
    "whatsapp.connect",
    "crm.manage",
    "audit.read",
    "auth.verify_token",
    "sessions.validate",
    "tenants.read",
    "tenants.manage",
    "members.manage",
    "api_keys.manage",
    "signing_keys.rotate",
    "service_accounts.manage",
]

BASE_ROLES = {
    "TENANT_OWNER": BASE_PERMISSIONS,
    "TENANT_ADMIN": ["users.read", "users.create", "roles.assign", "audit.read", "tenants.read", "members.manage", "api_keys.manage"],
    "MANAGER": ["users.read", "agents.create", "crm.manage"],
    "VENDEDOR": ["users.read", "crm.manage", "whatsapp.connect"],
    "AGENT_SUPERVISOR": ["users.read", "agents.create"],
    "AGENT_OPERATOR": ["agents.create", "whatsapp.connect"],
    "VIEWER": ["users.read"],
}


def assert_delegable(actor, role, permission_code=None):
    from rest_framework.exceptions import PermissionDenied

    owner = actor.membership_roles.filter(role__tenant_id=actor.tenant_id, role__code="TENANT_OWNER").exists()
    if role.tenant_id != actor.tenant_id:
        raise PermissionDenied("Role belongs to another workspace.")
    if not owner:
        granted = set(role.permissions.values_list("code", flat=True))
        if permission_code:
            granted.add(permission_code)
        if role.code == "TENANT_OWNER" or not granted.issubset(set(role_permissions_for_membership(actor))):
            raise PermissionDenied("Cannot grant or modify authority above your own role.")


def seed_permissions():
    from .models import Permission

    for code in BASE_PERMISSIONS:
        resource, action = code.split(".", 1)
        Permission.objects.get_or_create(code=code, defaults={"resource": resource, "action": action})


def seed_roles_for_tenant(tenant):
    from .models import Permission, RolePermission, TenantRole

    seed_permissions()
    for code, permissions in BASE_ROLES.items():
        role, _ = TenantRole.objects.get_or_create(
            tenant=tenant,
            code=code,
            defaults={"name": code.replace("_", " ").title(), "is_system": True},
        )
        for permission in Permission.objects.filter(code__in=permissions):
            RolePermission.objects.get_or_create(role=role, permission=permission)


def roles_for_membership(membership):
    if not membership:
        return []
    return list(membership.membership_roles.filter(role__tenant_id=membership.tenant_id).values_list("role__code", flat=True))


def role_permissions_for_membership(membership):
    if not membership:
        return []
    role_ids = membership.membership_roles.values_list("role_id", flat=True)
    return sorted(set(
        membership.tenant.roles.filter(id__in=role_ids)
        .values_list("permissions__code", flat=True)
        .exclude(permissions__code__isnull=True)
    ))


def permissions_for_membership(membership):
    if not membership:
        return []
    from apps.tenants.entitlements import entitlements_for_tenant

    role_permissions = set(role_permissions_for_membership(membership))
    entitlements = set(entitlements_for_tenant(membership.tenant))
    return sorted(role_permissions.intersection(entitlements))
