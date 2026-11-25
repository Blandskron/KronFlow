from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import decorators, permissions, status, views, viewsets

from apps.audit.models import AuditLog
from apps.audit.services import audit
from apps.shared.permissions import HasTenantPermission, IsPlatformAdminWithMfa, RequiresMfaForCriticalAction
from apps.shared.responses import ok
from apps.tenants.models import Tenant

from .models import APIKey, ServiceAccount, SigningKey
from .serializers import (
    APIKeyCreateSerializer,
    APIKeySerializer,
    ClientCredentialsSerializer,
    EmailConfirmSerializer,
    ForgotPasswordSerializer,
    InitialPasswordSerializer,
    MfaCodeSerializer,
    ResetPasswordSerializer,
    ServiceAccountCreateSerializer,
    ServiceAccountSerializer,
    SigningKeySerializer,
    TokenIntrospectionSerializer,
)
from .services import (
    create_api_key,
    create_service_account,
    generate_recovery_codes,
    introspect_token,
    issue_client_credentials_token,
    jwks_payload,
    rotate_api_key,
    rotate_signing_key,
    send_password_reset_email,
    send_verification_email,
    setup_totp,
    verify_totp,
)

User = get_user_model()


class ForgotPasswordView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "password"

    @extend_schema(tags=["Auth - Password"], request=ForgotPasswordSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if user:
            send_password_reset_email(user)
        else:
            audit(AuditLog.Event.PASSWORD_RESET_REQUESTED, request=request, email=serializer.validated_data["email"], user_exists=False)
        return ok({"sent": True})


class ResetPasswordView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "password"

    @extend_schema(tags=["Auth - Password"], request=ResetPasswordSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        audit(AuditLog.Event.PASSWORD_RESET_COMPLETED, request=request, user=user)
        audit(AuditLog.Event.PASSWORD_CHANGED, request=request, user=user)
        return ok({"reset": True})


class EmailResendView(views.APIView):
    throttle_scope = "password"

    @extend_schema(tags=["Auth - Email"], request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        send_verification_email(request.user)
        return ok({"sent": True})


class EmailConfirmView(views.APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["Auth - Email"], request=EmailConfirmSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = EmailConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        audit(AuditLog.Event.EMAIL_VERIFIED, request=request, user=user)
        audit(AuditLog.Event.ACCOUNT_ACTIVATED, request=request, user=user)
        return ok({"verified": True})


class InitialPasswordView(views.APIView):
    throttle_scope = "password"

    @extend_schema(tags=["Auth - Password"], request=InitialPasswordSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = InitialPasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        audit(AuditLog.Event.ACCOUNT_ACTIVATED, request=request, user=user, action="initial_password_set")
        return ok({"password_set": True, "sessions_revoked": True})


class MfaSetupView(views.APIView):
    throttle_scope = "mfa"

    @extend_schema(tags=["Auth - MFA"], request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        device, uri = setup_totp(request.user)
        audit(AuditLog.Event.MFA, request=request, action="setup_started")
        return ok({"secret": device.secret, "otpauth_uri": uri})


class MfaConfirmView(views.APIView):
    throttle_scope = "mfa"

    @extend_schema(tags=["Auth - MFA"], request=MfaCodeSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not verify_totp(request.user, serializer.validated_data["code"]):
            return JsonResponse({"success": False, "code": "MFA_INVALID_CODE", "message": "Codigo MFA invalido.", "details": {}}, status=400)
        request.user.mfa_device.confirmed_at = timezone.now()
        request.user.mfa_device.save(update_fields=["confirmed_at", "updated_at"])
        request.user.profile.mfa_enabled = True
        request.user.profile.mfa_confirmed_at = timezone.now()
        request.user.profile.save(update_fields=["mfa_enabled", "mfa_confirmed_at", "updated_at"])
        codes = generate_recovery_codes(request.user)
        audit(AuditLog.Event.MFA, request=request, action="confirmed")
        return ok({"confirmed": True, "recovery_codes": codes}, status=status.HTTP_201_CREATED)


class MfaVerifyView(views.APIView):
    throttle_scope = "mfa"

    @extend_schema(tags=["Auth - MFA"], request=MfaCodeSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return ok({"valid": verify_totp(request.user, serializer.validated_data["code"])})


class JwksView(views.APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["Security - JWKS"], request=None, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return ok(jwks_payload())


@extend_schema_view(
    list=extend_schema(tags=["Security - Signing Keys"]),
    retrieve=extend_schema(tags=["Security - Signing Keys"]),
    rotate=extend_schema(tags=["Security - Signing Keys"]),
)
class SigningKeyViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SigningKeySerializer
    permission_classes = [IsPlatformAdminWithMfa]

    def get_queryset(self):
        return SigningKey.objects.order_by("-created_at")

    @decorators.action(detail=False, methods=["post"])
    def rotate(self, request):
        key = rotate_signing_key(request=request)
        return ok(SigningKeySerializer(key).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(tags=["Security - Service Accounts"]),
    retrieve=extend_schema(tags=["Security - Service Accounts"]),
    create=extend_schema(tags=["Security - Service Accounts"]),
    update=extend_schema(tags=["Security - Service Accounts"]),
    partial_update=extend_schema(tags=["Security - Service Accounts"]),
    destroy=extend_schema(tags=["Security - Service Accounts"]),
)
class ServiceAccountViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceAccountSerializer
    permission_classes = [IsPlatformAdminWithMfa]

    def get_queryset(self):
        return ServiceAccount.objects.order_by("name")

    def create(self, request, *args, **kwargs):
        serializer = ServiceAccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = create_service_account(
            name=serializer.validated_data["name"],
            scopes=serializer.validated_data.get("scopes"),
            expires_at=serializer.validated_data.get("expires_at"),
            request=request,
        )
        data = ServiceAccountSerializer(account).data
        data["client_secret"] = account.plain_client_secret
        return ok(data, status=status.HTTP_201_CREATED)


class ClientCredentialsView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "machine"

    @extend_schema(tags=["Auth - Machine Credentials"], request=ClientCredentialsSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = ClientCredentialsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = issue_client_credentials_token(
                serializer.validated_data["client_id"],
                serializer.validated_data["client_secret"],
                serializer.validated_data.get("scopes"),
            )
        except (ServiceAccount.DoesNotExist, ValueError):
            return JsonResponse({"success": False, "code": "INVALID_CLIENT", "message": "Client credentials invalidas.", "details": {}}, status=401)
        return ok({"access_token": token, "token_type": "Bearer", "expires_in": 600})


class TokenIntrospectionView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "machine"

    @extend_schema(tags=["Auth - Token Introspection"], request=TokenIntrospectionSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return JsonResponse({"success": False, "code": "AUTH_REQUIRED", "message": "Service account token requerido.", "details": {}}, status=401)
        try:
            caller = introspect_token(authorization.removeprefix("Bearer ").strip())
        except Exception:
            return JsonResponse({"success": False, "code": "AUTH_INVALID_TOKEN", "message": "Service account token invalido.", "details": {}}, status=401)
        claims = caller.get("claims", {})
        if not caller.get("active") or claims.get("typ") != "service_account" or "auth.verify_token" not in claims.get("scopes", []):
            return JsonResponse({"success": False, "code": "FORBIDDEN_SCOPE", "message": "Scope auth.verify_token requerido.", "details": {}}, status=403)

        serializer = TokenIntrospectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return ok(introspect_token(serializer.validated_data["token"]))
        except Exception as exc:
            return ok({"active": False, "reason": exc.__class__.__name__})


@extend_schema_view(
    list=extend_schema(tags=["Security - API Keys"]),
    retrieve=extend_schema(tags=["Security - API Keys"]),
    create=extend_schema(tags=["Security - API Keys"]),
    update=extend_schema(tags=["Security - API Keys"]),
    partial_update=extend_schema(tags=["Security - API Keys"]),
    destroy=extend_schema(tags=["Security - API Keys"]),
    revoke=extend_schema(tags=["Security - API Keys"]),
    rotate=extend_schema(tags=["Security - API Keys"]),
)
class APIKeyViewSet(viewsets.ModelViewSet):
    serializer_class = APIKeySerializer
    permission_classes = [HasTenantPermission, RequiresMfaForCriticalAction]
    required_permission = "api_keys.manage"

    def get_queryset(self):
        tenant_id = getattr(self.request, "authorized_tenant_id", None)
        return APIKey.objects.filter(tenant_id=tenant_id).order_by("-created_at")

    def create(self, request):
        tenant_id = request.authorized_tenant_id
        tenant = Tenant.objects.get(id=tenant_id, memberships__user=request.user, memberships__status="active")
        serializer = APIKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        api_key = create_api_key(
            tenant=tenant,
            name=serializer.validated_data["name"],
            scopes=serializer.validated_data["scopes"],
            expires_at=serializer.validated_data.get("expires_at"),
            created_by=request.user,
            request=request,
        )
        data = APIKeySerializer(api_key).data
        data["key"] = api_key.plain_key
        return ok(data, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        api_key = self.get_object()
        api_key.status = APIKey.Status.REVOKED
        api_key.revoked_at = timezone.now()
        api_key.save(update_fields=["status", "revoked_at", "updated_at"])
        audit(AuditLog.Event.API_KEY_REVOKED, request=request, tenant=api_key.tenant, api_key=api_key.id)
        return ok({"revoked": True})

    @decorators.action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        replacement = rotate_api_key(self.get_object(), request=request)
        data = APIKeySerializer(replacement).data
        data["key"] = replacement.plain_key
        return ok(data, status=status.HTTP_201_CREATED)
