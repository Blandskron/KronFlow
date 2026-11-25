from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("active", "Activa"), ("revoked", "Revocada"), ("expired", "Expirada")], default="active", max_length=16)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("token_family", models.CharField(db_index=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="user_sessions", to="tenants.tenantmembership")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="user_sessions", to="tenants.tenant")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="iam_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "iam_user_session"},
        ),
        migrations.AddIndex(model_name="usersession", index=models.Index(fields=["user", "status"], name="iam_user_se_user_id_8a1b8b_idx")),
        migrations.AddIndex(model_name="usersession", index=models.Index(fields=["tenant", "status"], name="iam_user_se_tenant__5d8e5d_idx")),
        migrations.AddIndex(model_name="usersession", index=models.Index(fields=["expires_at"], name="iam_user_se_expires_746799_idx")),
    ]
