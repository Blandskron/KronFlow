from django.db import migrations


def seed_vendedor_role(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    Permission = apps.get_model("rbac", "Permission")
    TenantRole = apps.get_model("rbac", "TenantRole")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permissions = []
    for code in ("users.read", "crm.manage", "whatsapp.connect"):
        resource, action = code.split(".", 1)
        permission, _ = Permission.objects.get_or_create(
            code=code,
            defaults={"resource": resource, "action": action},
        )
        permissions.append(permission)

    for tenant in Tenant.objects.all():
        role, _ = TenantRole.objects.get_or_create(
            tenant=tenant,
            code="VENDEDOR",
            defaults={
                "name": "Vendedor",
                "description": "Acceso comercial para gestionar leads, conversaciones y WhatsApp.",
                "is_system": True,
            },
        )
        for permission in permissions:
            RolePermission.objects.get_or_create(role=role, permission=permission)


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0001_initial"),
        ("tenants", "0004_tenant_logo_invitation_rejection"),
    ]

    operations = [
        migrations.RunPython(seed_vendedor_role, migrations.RunPython.noop),
    ]
