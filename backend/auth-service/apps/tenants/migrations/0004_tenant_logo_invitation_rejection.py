from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0003_tenant_operational_runtime"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="logo_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="tenantinvitation",
            name="rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="tenantinvitation",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pendiente"),
                    ("accepted", "Aceptada"),
                    ("rejected", "Rechazada"),
                    ("expired", "Expirada"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
