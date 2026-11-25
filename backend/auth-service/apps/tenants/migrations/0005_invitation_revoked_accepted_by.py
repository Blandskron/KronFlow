from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenants", "0004_tenant_logo_invitation_rejection"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantinvitation",
            name="accepted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="accepted_tenant_invitations",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="tenantinvitation",
            name="revoked_at",
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
                    ("revoked", "Revocada"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
