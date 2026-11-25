from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("security", "0001_initial"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SigningKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kid", models.CharField(max_length=96, unique=True)),
                ("algorithm", models.CharField(default="RS256", max_length=16)),
                ("public_key", models.TextField()),
                ("encrypted_private_key", models.TextField()),
                ("status", models.CharField(choices=[("active", "Activa"), ("inactive", "Inactiva"), ("revoked", "Revocada")], default="active", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("rotated_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "iam_signing_key"},
        ),
        migrations.CreateModel(
            name="ServiceAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("client_id", models.CharField(max_length=96, unique=True)),
                ("secret_hash", models.CharField(max_length=128)),
                ("scopes", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(choices=[("active", "Activa"), ("disabled", "Deshabilitada"), ("revoked", "Revocada")], default="active", max_length=16)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "iam_service_account"},
        ),
        migrations.CreateModel(
            name="APIKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("prefix", models.CharField(db_index=True, max_length=16)),
                ("key_hash", models.CharField(max_length=128, unique=True)),
                ("scopes", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(choices=[("active", "Activa"), ("revoked", "Revocada"), ("expired", "Expirada")], default="active", max_length=16)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_keys", to="tenants.tenant")),
            ],
            options={"db_table": "iam_api_key"},
        ),
        migrations.AddIndex(model_name="signingkey", index=models.Index(fields=["kid", "status"], name="iam_signin_kid_9b9cc6_idx")),
        migrations.AddIndex(model_name="signingkey", index=models.Index(fields=["expires_at"], name="iam_signin_expires_14f7d1_idx")),
        migrations.AddIndex(model_name="serviceaccount", index=models.Index(fields=["client_id", "status"], name="iam_service_client__5034f7_idx")),
        migrations.AddIndex(model_name="apikey", index=models.Index(fields=["tenant", "status"], name="iam_api_key_tenant__808fcc_idx")),
        migrations.AddIndex(model_name="apikey", index=models.Index(fields=["prefix"], name="iam_api_key_prefix_11137d_idx")),
    ]
