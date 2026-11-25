from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("iam_sessions", "0001_initial"),
    ]

    operations = [
        migrations.AddField(model_name="usersession", name="last_refresh_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="usersession", name="risk_flags", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="usersession", name="risk_score", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AlterField(
            model_name="usersession",
            name="status",
            field=models.CharField(choices=[("active", "Activa"), ("revoked", "Revocada"), ("expired", "Expirada"), ("compromised", "Comprometida")], default="active", max_length=16),
        ),
    ]
