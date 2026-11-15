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
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event", models.CharField(choices=[("login_success", "Login exitoso"), ("login_failed", "Login fallido"), ("logout", "Logout"), ("refresh", "Refresh"), ("password_changed", "Password cambiado"), ("mfa", "MFA"), ("role_changed", "Rol cambiado"), ("member_changed", "Miembro cambiado"), ("session_revoked", "Sesion revocada")], max_length=64)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("correlation_id", models.CharField(blank=True, max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="tenants.tenant")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "iam_audit_log"},
        ),
        migrations.AddIndex(model_name="auditlog", index=models.Index(fields=["tenant", "event", "created_at"], name="iam_audit__tenant__25a23f_idx")),
        migrations.AddIndex(model_name="auditlog", index=models.Index(fields=["user", "created_at"], name="iam_audit__user_id_b696d8_idx")),
    ]
