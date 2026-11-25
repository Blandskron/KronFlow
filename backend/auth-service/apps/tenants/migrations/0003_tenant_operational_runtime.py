from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0002_tenant_subscription_entitlements"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantOperationalRuntime",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("schema_name", models.CharField(blank=True, max_length=63)),
                ("tenant_code", models.CharField(blank=True, max_length=64)),
                ("plan", models.CharField(blank=True, max_length=32)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pendiente"),
                            ("active", "Activo"),
                            ("suspended", "Suspendido"),
                            ("cancelled", "Cancelado"),
                            ("provision_failed", "Provision fallido"),
                        ],
                        default="pending",
                        max_length=32,
                    ),
                ),
                ("provisioned_at", models.DateTimeField(blank=True, null=True)),
                ("suspended_at", models.DateTimeField(blank=True, null=True)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="operational_runtime",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "iam_tenant_operational_runtime",
            },
        ),
        migrations.AddIndex(
            model_name="tenantoperationalruntime",
            index=models.Index(fields=["tenant_code"], name="iam_tenant_runtime_code_idx"),
        ),
        migrations.AddIndex(
            model_name="tenantoperationalruntime",
            index=models.Index(fields=["status"], name="iam_tenant_runtime_status_idx"),
        ),
    ]
