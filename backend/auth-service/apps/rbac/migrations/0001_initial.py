from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Permission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=96, unique=True)),
                ("resource", models.CharField(max_length=64)),
                ("action", models.CharField(max_length=64)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "iam_permission"},
        ),
        migrations.CreateModel(
            name="TenantRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=64)),
                ("name", models.CharField(max_length=128)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("is_system", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="roles", to="tenants.tenant")),
            ],
            options={"db_table": "iam_tenant_role"},
        ),
        migrations.CreateModel(
            name="MembershipRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="membership_roles", to="tenants.tenantmembership")),
                ("role", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="membership_roles", to="rbac.tenantrole")),
            ],
            options={"db_table": "iam_membership_role"},
        ),
        migrations.CreateModel(
            name="RolePermission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("permission", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="role_permissions", to="rbac.permission")),
                ("role", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="role_permissions", to="rbac.tenantrole")),
            ],
            options={"db_table": "iam_role_permission"},
        ),
        migrations.AddField(
            model_name="tenantrole",
            name="permissions",
            field=models.ManyToManyField(related_name="tenant_roles", through="rbac.RolePermission", to="rbac.permission"),
        ),
        migrations.AddIndex(model_name="permission", index=models.Index(fields=["resource", "action"], name="iam_permiss_resourc_7b7b23_idx")),
        migrations.AddConstraint(model_name="tenantrole", constraint=models.UniqueConstraint(fields=("tenant", "code"), name="uniq_tenant_role_code")),
        migrations.AddConstraint(model_name="membershiprole", constraint=models.UniqueConstraint(fields=("membership", "role"), name="uniq_membership_role")),
        migrations.AddConstraint(model_name="rolepermission", constraint=models.UniqueConstraint(fields=("role", "permission"), name="uniq_role_permission")),
    ]
