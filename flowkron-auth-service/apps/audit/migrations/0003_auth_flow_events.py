from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0002_advanced_security_events"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="event",
            field=models.CharField(
                choices=[
                    ("user_created", "Usuario creado"),
                    ("email_verification_sent", "Verificacion de email enviada"),
                    ("email_verified", "Email verificado"),
                    ("account_activated", "Cuenta activada"),
                    ("login_success", "Login exitoso"),
                    ("login_failed", "Login fallido"),
                    ("logout", "Logout"),
                    ("refresh", "Refresh"),
                    ("password_reset_requested", "Recuperacion solicitada"),
                    ("password_reset_completed", "Recuperacion completada"),
                    ("password_changed", "Password cambiado"),
                    ("mfa", "MFA"),
                    ("tenant_created", "Tenant creado"),
                    ("tenant_owner_assigned", "Owner asignado"),
                    ("invitation_sent", "Invitacion enviada"),
                    ("invitation_accepted", "Invitacion aceptada"),
                    ("invitation_expired", "Invitacion expirada"),
                    ("invitation_revoked", "Invitacion revocada"),
                    ("role_changed", "Rol cambiado"),
                    ("member_role_changed", "Rol de miembro cambiado"),
                    ("member_removed", "Miembro removido"),
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
