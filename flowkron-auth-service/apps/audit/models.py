from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    class Event(models.TextChoices):
        USER_CREATED = "user_created", "Usuario creado"
        EMAIL_VERIFICATION_SENT = "email_verification_sent", "Verificacion de email enviada"
        EMAIL_VERIFIED = "email_verified", "Email verificado"
        ACCOUNT_ACTIVATED = "account_activated", "Cuenta activada"
        LOGIN_SUCCESS = "login_success", "Login exitoso"
        LOGIN_FAILED = "login_failed", "Login fallido"
        LOGOUT = "logout", "Logout"
        REFRESH = "refresh", "Refresh"
        PASSWORD_RESET_REQUESTED = "password_reset_requested", "Recuperacion solicitada"
        PASSWORD_RESET_COMPLETED = "password_reset_completed", "Recuperacion completada"
        PASSWORD_CHANGED = "password_changed", "Password cambiado"
        MFA = "mfa", "MFA"
        TENANT_CREATED = "tenant_created", "Tenant creado"
        TENANT_OWNER_ASSIGNED = "tenant_owner_assigned", "Owner asignado"
        INVITATION_SENT = "invitation_sent", "Invitacion enviada"
        INVITATION_ACCEPTED = "invitation_accepted", "Invitacion aceptada"
        INVITATION_EXPIRED = "invitation_expired", "Invitacion expirada"
        INVITATION_REVOKED = "invitation_revoked", "Invitacion revocada"
        ROLE_CHANGED = "role_changed", "Rol cambiado"
        MEMBER_ROLE_CHANGED = "member_role_changed", "Rol de miembro cambiado"
        MEMBER_REMOVED = "member_removed", "Miembro removido"
        MEMBER_CHANGED = "member_changed", "Miembro cambiado"
        SESSION_REVOKED = "session_revoked", "Sesion revocada"
        SIGNING_KEY_ROTATED = "signing_key_rotated", "Clave JWT rotada"
        API_KEY_CREATED = "api_key_created", "API key creada"
        API_KEY_REVOKED = "api_key_revoked", "API key revocada"
        API_KEY_ROTATED = "api_key_rotated", "API key rotada"
        SERVICE_ACCOUNT_CREATED = "service_account_created", "Service account creada"
        SESSION_RISK_DETECTED = "session_risk_detected", "Riesgo de sesion detectado"
        SESSION_COMPROMISED = "session_compromised", "Sesion comprometida"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    tenant = models.ForeignKey("tenants.Tenant", null=True, blank=True, on_delete=models.SET_NULL)
    event = models.CharField(max_length=64, choices=Event.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    correlation_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iam_audit_log"
        indexes = [
            models.Index(fields=["tenant", "event", "created_at"], name="iam_audit__tenant__25a23f_idx"),
            models.Index(fields=["user", "created_at"], name="iam_audit__user_id_b696d8_idx"),
        ]
