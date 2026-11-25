from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.accounts.models import UserProfile
from apps.security.services import verify_totp
from apps.tenants.models import Tenant, TenantMembership

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            "display_name",
            "phone",
            "avatar_url",
            "timezone",
            "locale",
            "email_verified_at",
            "account_activated_at",
            "initial_password_set_at",
            "onboarding_completed_at",
            "mfa_enabled",
            "mfa_confirmed_at",
        ]
        read_only_fields = [
            "email_verified_at",
            "account_activated_at",
            "initial_password_set_at",
            "onboarding_completed_at",
            "mfa_enabled",
            "mfa_confirmed_at",
        ]


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source="user.first_name", required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(source="user.last_name", required=False, allow_blank=True, max_length=150)

    class Meta:
        model = UserProfile
        fields = ["display_name", "phone", "avatar_url", "timezone", "locale", "first_name", "last_name"]

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if user_data:
            for field, value in user_data.items():
                setattr(instance.user, field, value)
            instance.user.save(update_fields=[*user_data.keys()])
        return instance


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_active", "profile"]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    tenant_id = serializers.IntegerField(required=False)
    mfa_code = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        email = attrs["email"].lower()
        usernames = list(User.objects.filter(email__iexact=email).values_list("username", flat=True)[:2])
        username = usernames[0] if len(usernames) == 1 else email
        user = authenticate(self.context["request"], username=username, password=attrs["password"])
        if not user:
            raise serializers.ValidationError("Credenciales invalidas.", code="AUTH_INVALID_CREDENTIALS")
        if not user.is_active:
            raise serializers.ValidationError("Usuario inactivo.", code="AUTH_USER_INACTIVE")
        profile = getattr(user, "profile", None)
        if not profile or not profile.email_verified_at:
            raise serializers.ValidationError("Email no verificado.", code="AUTH_EMAIL_NOT_VERIFIED")
        if profile.mfa_enabled and not verify_totp(user, attrs.get("mfa_code", "")):
            raise serializers.ValidationError("MFA requerido.", code="MFA_REQUIRED")
        memberships = user.memberships.filter(status=TenantMembership.Status.ACTIVE, tenant__status=Tenant.Status.ACTIVE)
        if attrs.get("tenant_id"):
            memberships = memberships.filter(tenant_id=attrs["tenant_id"])
        membership = memberships.first()
        attrs["user"] = user
        attrs["membership"] = membership
        attrs["onboarding_required"] = membership is None
        attrs["amr"] = "mfa" if profile.mfa_enabled else "pwd"
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value

    def validate(self, attrs):
        if not self.context["request"].user.check_password(attrs["current_password"]):
            raise serializers.ValidationError("Password actual incorrecto.", code="AUTH_INVALID_PASSWORD")
        return attrs
