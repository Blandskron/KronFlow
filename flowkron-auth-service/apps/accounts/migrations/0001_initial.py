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
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("display_name", models.CharField(blank=True, max_length=160)),
                ("phone", models.CharField(blank=True, max_length=32)),
                ("avatar_url", models.URLField(blank=True)),
                ("timezone", models.CharField(default="America/Santiago", max_length=64)),
                ("locale", models.CharField(default="es-CL", max_length=16)),
                ("email_verified_at", models.DateTimeField(blank=True, null=True)),
                ("mfa_enabled", models.BooleanField(default=False)),
                ("mfa_confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profile", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "iam_user_profile"},
        ),
    ]
