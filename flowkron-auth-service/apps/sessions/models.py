import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class UserSessionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=UserSession.Status.ACTIVE, expires_at__gt=timezone.now())


class UserSessionManager(models.Manager):
    def get_queryset(self):
        return UserSessionQuerySet(self.model, using=self._db)

    def create_from_request(self, user, membership, request):
        return self.create(
            user=user,
            membership=membership,
            tenant=membership.tenant if membership else None,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            expires_at=timezone.now() + timezone.timedelta(days=14),
            token_family=str(uuid.uuid4()),
        )


class UserSession(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        REVOKED = "revoked", "Revocada"
        EXPIRED = "expired", "Expirada"
        COMPROMISED = "compromised", "Comprometida"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="iam_sessions", on_delete=models.CASCADE)
    tenant = models.ForeignKey("tenants.Tenant", null=True, blank=True, related_name="user_sessions", on_delete=models.CASCADE)
    membership = models.ForeignKey("tenants.TenantMembership", null=True, blank=True, related_name="user_sessions", on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    risk_score = models.PositiveSmallIntegerField(default=0)
    risk_flags = models.JSONField(default=list, blank=True)
    last_refresh_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    token_family = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserSessionManager()

    class Meta:
        db_table = "iam_user_session"
        indexes = [
            models.Index(fields=["user", "status"], name="iam_user_se_user_id_8a1b8b_idx"),
            models.Index(fields=["tenant", "status"], name="iam_user_se_tenant__5d8e5d_idx"),
            models.Index(fields=["expires_at"], name="iam_user_se_expires_746799_idx"),
        ]

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE and self.expires_at > timezone.now()
