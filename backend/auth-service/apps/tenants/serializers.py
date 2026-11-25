import secrets
import hashlib

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.rbac.models import MembershipRole, TenantRole
from apps.rbac.services import assert_delegable, permissions_for_membership

from .models import Tenant, TenantInvitation, TenantMembership
from .entitlements import subscription_summary

User = get_user_model()


WHATSAPP_STATUSES = ("disconnected", "connecting", "qr_pending", "connected", "pairing_required")


class WhatsAppTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=WHATSAPP_STATUSES)
    changed_at = serializers.DateTimeField()


class WhatsAppDiagnosticSerializer(serializers.Serializer):
    status_changed_at = serializers.DateTimeField()
    recent_transitions = WhatsAppTransitionSerializer(many=True, required=False, max_length=8)
    last_connected_at = serializers.DateTimeField(required=False)
    disconnect_cause = serializers.ChoiceField(choices=(
        "signed_out", "invalid_session", "replaced_session", "provider_denied", "device_mismatch",
        "temporary", "startup_failed", "workspace_unavailable", "manual",
    ), required=False)
    retry_attempts = serializers.IntegerField(min_value=0, max_value=100)
    retry_limit = serializers.IntegerField(min_value=1, max_value=100)
    next_retry_at = serializers.DateTimeField(required=False)
    retry_exhausted = serializers.BooleanField()
    next_action = serializers.ChoiceField(choices=("connect", "scan", "wait", "retry", "relink", "none"))
    qr_issued_at = serializers.DateTimeField(required=False)
    qr_expires_at = serializers.DateTimeField(required=False)


class WhatsAppSessionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=WHATSAPP_STATUSES)
    qr = serializers.CharField(required=False, max_length=32768)
    diagnostics = WhatsAppDiagnosticSerializer(required=False)


class TenantSerializer(serializers.ModelSerializer):
    subscription = serializers.SerializerMethodField()
    operational_runtime = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            "id",
            "slug",
            "name",
            "legal_name",
            "tax_id",
            "logo_url",
            "country",
            "status",
            "plan",
            "subscription_status",
            "subscription_provider",
            "subscription_external_id",
            "subscription_current_period_end",
            "subscription",
            "operational_runtime",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "slug",
            "status",
            "plan",
            "subscription_status",
            "subscription_provider",
            "subscription_external_id",
            "subscription_current_period_end",
            "subscription",
            "operational_runtime",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_subscription(self, obj):
        return subscription_summary(obj)

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_operational_runtime(self, obj):
        runtime = getattr(obj, "operational_runtime", None)
        if not runtime:
            return None
        return {
            "schema_name": runtime.schema_name,
            "tenant_code": runtime.tenant_code,
            "plan": runtime.plan,
            "status": runtime.status,
            "provisioned_at": runtime.provisioned_at,
            "suspended_at": runtime.suspended_at,
            "last_sync_at": runtime.last_sync_at,
            "last_error": runtime.last_error,
        }


class TenantOnboardingSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=180)
    legal_name = serializers.CharField(max_length=220, required=False, allow_blank=True)
    tax_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    country = serializers.CharField(max_length=2, required=False, default="CL")


class TenantMembershipSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    display_name = serializers.CharField(source="user.profile.display_name", read_only=True)
    avatar_url = serializers.CharField(source="user.profile.avatar_url", read_only=True)
    role_codes = serializers.SerializerMethodField()

    class Meta:
        model = TenantMembership
        fields = [
            "id",
            "tenant",
            "user",
            "user_email",
            "display_name",
            "avatar_url",
            "role_codes",
            "status",
            "joined_at",
            "revoked_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["joined_at", "revoked_at", "created_at", "updated_at"]

    def get_role_codes(self, obj):
        return list(obj.membership_roles.select_related("role").values_list("role__code", flat=True))


class TenantInvitationSerializer(serializers.ModelSerializer):
    invited_by_email = serializers.EmailField(source="invited_by.email", read_only=True)
    accepted_by_email = serializers.EmailField(source="accepted_by.email", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = TenantInvitation
        fields = [
            "id",
            "tenant",
            "tenant_name",
            "email",
            "role_code",
            "status",
            "invited_by_email",
            "accepted_by_email",
            "expires_at",
            "accepted_at",
            "rejected_at",
            "revoked_at",
            "created_at",
        ]
        read_only_fields = fields


class InviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role_code = serializers.CharField(default="VIEWER")
    expires_in_days = serializers.IntegerField(default=7, min_value=1, max_value=30)

    def validate_role_code(self, value):
        tenant = self.context["tenant"]
        if not TenantRole.objects.filter(tenant=tenant, code=value).exists():
            raise serializers.ValidationError("Rol no existe en este tenant.", code="ROLE_NOT_FOUND")
        assert_delegable(self.context["request"].authorized_membership, TenantRole.objects.get(tenant=tenant, code=value))
        return value

    def create(self, validated_data):
        tenant = self.context["tenant"]
        email = validated_data["email"].lower()
        token = secrets.token_urlsafe(32)
        TenantInvitation.objects.filter(tenant=tenant, email=email, status=TenantInvitation.Status.PENDING).update(
            status=TenantInvitation.Status.EXPIRED
        )
        invitation = TenantInvitation.objects.create(
            tenant=tenant,
            email=email,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            role_code=validated_data["role_code"],
            invited_by=self.context["request"].user,
            expires_at=timezone.now() + timezone.timedelta(days=validated_data["expires_in_days"]),
        )
        invitation.plain_token = token
        invitation.invite_url = invitation_url(token)
        invitation.email_sent = send_invitation_email(invitation, token)
        return invitation


class InvitationTokenSerializer(serializers.Serializer):
    token = serializers.CharField()


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.CharField()
    display_name = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, write_only=True)

    def validate_password(self, value):
        django_validate_password(value)
        return value

    @transaction.atomic
    def save(self, **kwargs):
        request = self.context["request"]
        invitation = get_pending_invitation(self.validated_data["token"])
        tenant = Tenant.objects.select_for_update().get(pk=invitation.tenant_id)
        invitation = get_pending_invitation(self.validated_data["token"])
        inviter = tenant.memberships.filter(user=invitation.invited_by, status=TenantMembership.Status.ACTIVE).first()
        role = tenant.roles.filter(code=invitation.role_code).first()
        if tenant.status != Tenant.Status.ACTIVE or not inviter or not role or "members.manage" not in permissions_for_membership(inviter):
            raise serializers.ValidationError("La invitacion ya no puede conceder acceso.", code="INVITATION_INVALID")
        assert_delegable(inviter, role)

        email = invitation.email
        user = request.user if request.user and request.user.is_authenticated else None
        existing_user = User.objects.filter(email__iexact=email).first()
        if user and user.email.lower() != email.lower():
            raise serializers.ValidationError("La invitacion no corresponde al usuario autenticado.", code="INVITATION_EMAIL_MISMATCH")
        if not user and existing_user:
            raise serializers.ValidationError("Debes iniciar sesion para aceptar la invitacion.", code="AUTH_REQUIRED")
        if not user:
            password = self.validated_data.get("password")
            if not password:
                raise serializers.ValidationError("Password requerido para activar la cuenta invitada.", code="PASSWORD_REQUIRED")
            user = User(username=email, email=email)
            user._skip_email_verification = True
            user.set_password(password)
            user.save()
            profile = user.profile
            profile.email_verified_at = timezone.now()
            profile.account_activated_at = profile.email_verified_at
            profile.initial_password_set_at = profile.email_verified_at
            profile.save(update_fields=["email_verified_at", "account_activated_at", "initial_password_set_at", "updated_at"])
            self.created_user = user
        else:
            self.created_user = None
            profile = getattr(user, "profile", None)
            if not profile or not profile.email_verified_at:
                raise serializers.ValidationError("Debes verificar tu correo antes de aceptar la invitacion.", code="AUTH_EMAIL_NOT_VERIFIED")
        if self.validated_data.get("display_name") and not user.profile.display_name:
            user.profile.display_name = self.validated_data["display_name"]
            user.profile.save(update_fields=["display_name", "updated_at"])
        membership, created = TenantMembership.objects.get_or_create(
            user=user,
            tenant=invitation.tenant,
            defaults={"status": TenantMembership.Status.ACTIVE, "joined_at": timezone.now()},
        )
        if not created and membership.status != TenantMembership.Status.ACTIVE:
            # A new invitation grants only its selected role, never the revoked grants.
            membership.membership_roles.all().delete()
            membership.status = TenantMembership.Status.ACTIVE
            membership.joined_at = timezone.now()
            membership.revoked_at = None
            membership.save(update_fields=["status", "joined_at", "revoked_at", "updated_at"])
        if not user.profile.onboarding_completed_at:
            user.profile.onboarding_completed_at = timezone.now()
            user.profile.save(update_fields=["onboarding_completed_at", "updated_at"])
        MembershipRole.objects.get_or_create(membership=membership, role=role)
        invitation.status = TenantInvitation.Status.ACCEPTED
        invitation.accepted_at = timezone.now()
        invitation.accepted_by = user
        invitation.save(update_fields=["status", "accepted_at", "accepted_by"])
        return membership


class MemberUpdateSerializer(serializers.Serializer):
    role_codes = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=False)
    status = serializers.ChoiceField(choices=TenantMembership.Status.choices, required=False)

    def validate_role_codes(self, value):
        tenant = self.context["membership"].tenant
        existing = set(TenantRole.objects.filter(tenant=tenant, code__in=value).values_list("code", flat=True))
        missing = sorted(set(value) - existing)
        if missing:
            raise serializers.ValidationError(f"Roles no existen en este tenant: {', '.join(missing)}")
        return value

    def save(self, **kwargs):
        membership = self.context["membership"]
        if "status" in self.validated_data:
            membership.status = self.validated_data["status"]
            if membership.status == TenantMembership.Status.ACTIVE and not membership.joined_at:
                membership.joined_at = timezone.now()
            if membership.status in {TenantMembership.Status.REVOKED, TenantMembership.Status.SUSPENDED}:
                membership.revoked_at = timezone.now()
            membership.save(update_fields=["status", "joined_at", "revoked_at", "updated_at"])
        if "role_codes" in self.validated_data:
            MembershipRole.objects.filter(membership=membership).delete()
            roles = TenantRole.objects.filter(tenant=membership.tenant, code__in=self.validated_data["role_codes"])
            for role in roles:
                MembershipRole.objects.create(membership=membership, role=role)
        return membership


def get_pending_invitation(token: str) -> TenantInvitation:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    invitation = TenantInvitation.objects.select_related("tenant", "invited_by").filter(
        token_hash=token_hash,
        status=TenantInvitation.Status.PENDING,
    ).first()
    if not invitation:
        raise serializers.ValidationError("Invitacion invalida.", code="INVITATION_INVALID")
    if invitation.expires_at < timezone.now():
        invitation.status = TenantInvitation.Status.EXPIRED
        invitation.save(update_fields=["status"])
        raise serializers.ValidationError("Invitacion expirada.", code="INVITATION_EXPIRED")
    return invitation


def invitation_url(token: str) -> str:
    return f"{settings.APP_PUBLIC_URL.rstrip('/')}/login?invitation_token={token}"


def send_invitation_email(invitation: TenantInvitation, token: str) -> bool:
    inviter = invitation.invited_by.email if invitation.invited_by else "Flowkron"
    url = invitation_url(token)
    subject = f"Has sido invitado a {invitation.tenant.name}"
    message = (
        f"Has sido invitado como {invitation.role_code} a la empresa {invitation.tenant.name}.\n\n"
        f"Invitado por: {inviter}\n\n"
        f"Si ya tienes usuario, inicia sesion y acepta la invitacion con este enlace:\n{url}\n\n"
        f"Si aun no tienes usuario, usa este enlace para activar la cuenta invitada con este mismo correo.\n\n"
        f"Esta invitacion vence el {invitation.expires_at:%Y-%m-%d %H:%M}."
    )
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [invitation.email], fail_silently=False)
    except Exception:
        return False
    return True
