from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="event",
            field=models.CharField(
                choices=[
                    ("login_success", "Login exitoso"),
                    ("login_failed", "Login fallido"),
                    ("logout", "Logout"),
                    ("refresh", "Refresh"),
                    ("password_changed", "Password cambiado"),
                    ("mfa", "MFA"),
                    ("role_changed", "Rol cambiado"),
                    ("member_changed", "Miembro cambiado"),
                    ("session_revoked", "Sesion revocada"),
                    ("signing_key_rotated", "Clave JWT rotada"),
                    ("api_key_created", "API key creada"),
                    ("api_key_revoked", "API key revocada"),
                    ("api_key_rotated", "API key rotada"),
                    ("service_account_created", "Service account creada"),
                    ("session_risk_detected", "Riesgo de sesion detectado"),
                    ("session_compromised", "Sesion comprometida"),
                ],
                max_length=64,
            ),
        ),
    ]
