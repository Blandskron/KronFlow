from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Tenant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(blank=True, max_length=120, unique=True)),
                ("name", models.CharField(max_length=180)),
                ("legal_name", models.CharField(max_length=220)),
                ("tax_id", models.CharField(blank=True, max_length=64)),
                ("country", models.CharField(default="CL", max_length=2)),
                ("status", models.CharField(choices=[("active", "Activo"), ("suspended", "Suspendido"), ("archived", "Archivado")], default="active", max_length=16)),
                ("plan", models.CharField(choices=[("free", "Free"), ("starter", "Starter"), ("pro", "Pro"), ("enterprise", "Enterprise")], default="starter", max_length=24)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "iam_tenant"},
        ),
        migrations.CreateModel(
            name="TenantMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("invited", "Invitado"), ("active", "Activo"), ("suspended", "Suspendido"), ("revoked", "Revocado")], default="invited", max_length=16)),
                ("joined_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("invited_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sent_invitations", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="tenants.tenant")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "iam_tenant_membership"},
        ),
        migrations.CreateModel(
            name="TenantInvitation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254)),
                ("token_hash", models.CharField(max_length=128, unique=True)),
                ("role_code", models.CharField(default="VIEWER", max_length=64)),
                ("status", models.CharField(default="pending", max_length=16)),
                ("expires_at", models.DateTimeField()),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("invited_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invitations", to="tenants.tenant")),
            ],
            options={"db_table": "iam_tenant_invitation"},
        ),
        migrations.AddIndex(model_name="tenant", index=models.Index(fields=["slug"], name="iam_tenant_slug_idx")),
        migrations.AddIndex(model_name="tenant", index=models.Index(fields=["status"], name="iam_tenant_status_idx")),
        migrations.AddIndex(model_name="tenantmembership", index=models.Index(fields=["tenant", "status"], name="iam_tenant__tenant__6c2d52_idx")),
        migrations.AddIndex(model_name="tenantmembership", index=models.Index(fields=["user", "status"], name="iam_tenant__user_id_7cf82c_idx")),
        migrations.AddConstraint(model_name="tenantmembership", constraint=models.UniqueConstraint(fields=("user", "tenant"), name="uniq_user_tenant_membership")),
        migrations.AddIndex(model_name="tenantinvitation", index=models.Index(fields=["tenant", "email", "status"], name="iam_tenant__tenant__1e3f3a_idx")),
    ]
