from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Tenant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        SUSPENDED = "suspended", "Suspendido"
        ARCHIVED = "archived", "Archivado"

    class Plan(models.TextChoices):
        FREE = "free", "Free"
        STARTER = "starter", "Starter"
        PRO = "pro", "Pro"
        ENTERPRISE = "enterprise", "Enterprise"

    class SubscriptionStatus(models.TextChoices):
        FREE = "free", "Free"
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"
        UNPAID = "unpaid", "Unpaid"

    slug = models.SlugField(max_length=120, unique=True, blank=True)
    name = models.CharField(max_length=180)
    legal_name = models.CharField(max_length=220)
    tax_id = models.CharField(max_length=64, blank=True)
    logo_url = models.URLField(blank=True)
    country = models.CharField(max_length=2, default="CL")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    plan = models.CharField(max_length=24, choices=Plan.choices, default=Plan.FREE)
    subscription_status = models.CharField(max_length=24, choices=SubscriptionStatus.choices, default=SubscriptionStatus.FREE)
    subscription_provider = models.CharField(max_length=64, blank=True)
    subscription_external_id = models.CharField(max_length=160, blank=True)
    subscription_current_period_end = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "iam_tenant"
        indexes = [
            models.Index(fields=["slug"], name="iam_tenant_slug_idx"),
            models.Index(fields=["status"], name="iam_tenant_status_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:110]
            base = self.slug
            suffix = 1
            while Tenant.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                suffix += 1
                self.slug = f"{base}-{suffix}"[:120]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class TenantMembership(models.Model):
    class Status(models.TextChoices):
        INVITED = "invited", "Invitado"
        ACTIVE = "active", "Activo"
        SUSPENDED = "suspended", "Suspendido"
        REVOKED = "revoked", "Revocado"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="memberships", on_delete=models.CASCADE)
    tenant = models.ForeignKey(Tenant, related_name="memberships", on_delete=models.CASCADE)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.INVITED)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="sent_invitations", on_delete=models.SET_NULL)
    joined_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "iam_tenant_membership"
        constraints = [models.UniqueConstraint(fields=["user", "tenant"], name="uniq_user_tenant_membership")]
        indexes = [
            models.Index(fields=["tenant", "status"], name="iam_tenant__tenant__6c2d52_idx"),
            models.Index(fields=["user", "status"], name="iam_tenant__user_id_7cf82c_idx"),
        ]

    def __str__(self):
        return f"{self.user_id}@{self.tenant_id}"


class TenantInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        ACCEPTED = "accepted", "Aceptada"
        REJECTED = "rejected", "Rechazada"
        EXPIRED = "expired", "Expirada"
        REVOKED = "revoked", "Revocada"

    tenant = models.ForeignKey(Tenant, related_name="invitations", on_delete=models.CASCADE)
    email = models.EmailField()
    token_hash = models.CharField(max_length=128, unique=True)
    role_code = models.CharField(max_length=64, default="VIEWER")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="accepted_tenant_invitations", on_delete=models.SET_NULL)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iam_tenant_invitation"
        indexes = [models.Index(fields=["tenant", "email", "status"], name="iam_tenant__tenant__1e3f3a_idx")]


class TenantOperationalRuntime(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        ACTIVE = "active", "Activo"
        SUSPENDED = "suspended", "Suspendido"
        CANCELLED = "cancelled", "Cancelado"
        PROVISION_FAILED = "provision_failed", "Provision fallido"

    tenant = models.OneToOneField(Tenant, related_name="operational_runtime", on_delete=models.CASCADE)
    schema_name = models.CharField(max_length=63, blank=True)
    tenant_code = models.CharField(max_length=64, blank=True)
    plan = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    provisioned_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "iam_tenant_operational_runtime"
        indexes = [
            models.Index(fields=["tenant_code"], name="iam_tenant_runtime_code_idx"),
            models.Index(fields=["status"], name="iam_tenant_runtime_status_idx"),
        ]

    def __str__(self):
        return f"{self.tenant_id}:{self.status}"
