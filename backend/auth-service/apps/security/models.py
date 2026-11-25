from django.conf import settings
from django.db import models


class SigningKey(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        INACTIVE = "inactive", "Inactiva"
        REVOKED = "revoked", "Revocada"

    kid = models.CharField(max_length=96, unique=True)
    algorithm = models.CharField(max_length=16, default="RS256")
    public_key = models.TextField()
    encrypted_private_key = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "iam_signing_key"
        indexes = [
            models.Index(fields=["kid", "status"], name="iam_signin_kid_9b9cc6_idx"),
            models.Index(fields=["expires_at"], name="iam_signin_expires_14f7d1_idx"),
        ]

    def __str__(self):
        return self.kid


class ServiceAccount(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        DISABLED = "disabled", "Deshabilitada"
        REVOKED = "revoked", "Revocada"

    name = models.CharField(max_length=120)
    client_id = models.CharField(max_length=96, unique=True)
    secret_hash = models.CharField(max_length=128)
    scopes = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "iam_service_account"
        indexes = [models.Index(fields=["client_id", "status"], name="iam_service_client__5034f7_idx")]

    def __str__(self):
        return self.name


class APIKey(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        REVOKED = "revoked", "Revocada"
        EXPIRED = "expired", "Expirada"

    tenant = models.ForeignKey("tenants.Tenant", related_name="api_keys", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    prefix = models.CharField(max_length=16, db_index=True)
    key_hash = models.CharField(max_length=128, unique=True)
    scopes = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "iam_api_key"
        indexes = [
            models.Index(fields=["tenant", "status"], name="iam_api_key_tenant__808fcc_idx"),
            models.Index(fields=["prefix"], name="iam_api_key_prefix_11137d_idx"),
        ]

    def __str__(self):
        return f"{self.tenant_id}:{self.name}"


class EmailVerificationToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="email_tokens", on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=128, unique=True)
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iam_email_verification_token"


class PasswordResetToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="password_reset_tokens", on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=128, unique=True)
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iam_password_reset_token"


class MfaDevice(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="mfa_device", on_delete=models.CASCADE)
    secret = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "iam_mfa_device"


class MfaRecoveryCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="mfa_recovery_codes", on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=128)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iam_mfa_recovery_code"
        indexes = [models.Index(fields=["user", "used_at"], name="iam_mfa_rec_user_id_f265d3_idx")]
