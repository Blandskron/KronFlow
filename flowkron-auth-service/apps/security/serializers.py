from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from apps.sessions.models import UserSession

from .models import APIKey, EmailVerificationToken, PasswordResetToken, ServiceAccount, SigningKey
from .services import hash_token

User = get_user_model()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def save(self, **kwargs):
        reset = PasswordResetToken.objects.select_related("user").filter(token_hash=hash_token(self.validated_data["token"]), used_at__isnull=True).first()
        if not reset:
            raise serializers.ValidationError("Token invalido.", code="TOKEN_INVALID")
        if reset.expires_at < timezone.now():
            raise serializers.ValidationError("Token expirado.", code="TOKEN_EXPIRED")
        reset.user.set_password(self.validated_data["new_password"])
        reset.user.save(update_fields=["password"])
        reset.used_at = timezone.now()
        reset.save(update_fields=["used_at"])
        UserSession.objects.filter(user=reset.user).update(status=UserSession.Status.REVOKED, revoked_at=timezone.now())
        return reset.user


class EmailConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(required=False, write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def save(self, **kwargs):
        email_token = EmailVerificationToken.objects.select_related("user").filter(token_hash=hash_token(self.validated_data["token"]), used_at__isnull=True).first()
        if not email_token:
            raise serializers.ValidationError("Token invalido.", code="TOKEN_INVALID")
        if email_token.expires_at < timezone.now():
            raise serializers.ValidationError("Token expirado.", code="TOKEN_EXPIRED")
        email_token.user.profile.email_verified_at = timezone.now()
        if not email_token.user.profile.account_activated_at:
            email_token.user.profile.account_activated_at = timezone.now()
        if self.validated_data.get("new_password"):
            email_token.user.set_password(self.validated_data["new_password"])
            email_token.user.save(update_fields=["password"])
            email_token.user.profile.initial_password_set_at = timezone.now()
        profile_fields = ["email_verified_at", "account_activated_at", "updated_at"]
        if self.validated_data.get("new_password"):
            profile_fields.append("initial_password_set_at")
        email_token.user.profile.save(update_fields=profile_fields)
        email_token.used_at = timezone.now()
        email_token.save(update_fields=["used_at"])
        return email_token.user


class InitialPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        user.profile.initial_password_set_at = timezone.now()
        if not user.profile.account_activated_at:
            user.profile.account_activated_at = timezone.now()
        user.profile.save(update_fields=["initial_password_set_at", "account_activated_at", "updated_at"])
        UserSession.objects.filter(user=user).update(status=UserSession.Status.REVOKED, revoked_at=timezone.now())
        return user


class MfaCodeSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=12)


class SigningKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = SigningKey
        fields = ["id", "kid", "algorithm", "status", "created_at", "expires_at", "rotated_at"]
        read_only_fields = fields


class ServiceAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceAccount
        fields = ["id", "name", "client_id", "scopes", "status", "expires_at", "last_used_at", "created_at", "updated_at"]
        read_only_fields = ["client_id", "last_used_at", "created_at", "updated_at"]


class ServiceAccountCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    scopes = serializers.ListField(child=serializers.CharField(), required=False)
    expires_at = serializers.DateTimeField(required=False)


class ClientCredentialsSerializer(serializers.Serializer):
    client_id = serializers.CharField()
    client_secret = serializers.CharField(write_only=True)
    scopes = serializers.ListField(child=serializers.CharField(), required=False)


class APIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ["id", "tenant", "name", "prefix", "scopes", "status", "expires_at", "last_used_at", "revoked_at", "created_at"]
        read_only_fields = fields


class APIKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    scopes = serializers.ListField(child=serializers.CharField())
    expires_at = serializers.DateTimeField(required=False)


class TokenIntrospectionSerializer(serializers.Serializer):
    token = serializers.CharField()
