from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("iam_sessions", "0002_session_risk"),
        ("tenants", "0005_invitation_revoked_accepted_by"),
    ]

    operations = [
        migrations.AlterField(
            model_name="usersession",
            name="membership",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_sessions",
                to="tenants.tenantmembership",
            ),
        ),
        migrations.AlterField(
            model_name="usersession",
            name="tenant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_sessions",
                to="tenants.tenant",
            ),
        ),
    ]
