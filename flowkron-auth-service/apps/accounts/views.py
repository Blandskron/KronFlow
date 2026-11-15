from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ErrorDetail
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import parsers, permissions, status, views
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from apps.audit.models import AuditLog
from apps.audit.services import audit
from apps.rbac.services import permissions_for_membership, roles_for_membership
from apps.sessions.models import UserSession
from apps.shared.responses import ok
from apps.shared.image_uploads import absolute_media_url, save_uploaded_image
from apps.tenants.entitlements import subscription_summary
from apps.tenants.models import TenantMembership
from apps.tenants.serializers import TenantMembershipSerializer, TenantSerializer

from .serializers import LoginSerializer, PasswordChangeSerializer, UserProfileUpdateSerializer, UserSerializer
from .tokens import FlowkronRefreshToken, issue_tokens

User = get_user_model()


class LoginView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "login"

    @extend_schema(tags=["Auth - Users"], request=LoginSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            audit(AuditLog.Event.LOGIN_FAILED, request=request, email=request.data.get("email"))
            code = _first_error_code(serializer.errors) or "AUTH_INVALID_CREDENTIALS"
            message_by_code = {
                "AUTH_EMAIL_NOT_VERIFIED": "Debes verificar tu correo antes de iniciar sesion.",
                "MFA_REQUIRED": "MFA requerido.",
                "AUTH_USER_INACTIVE": "Usuario inactivo.",
            }
            return Response(
                {
                    "success": False,
                    "code": code,
                    "message": message_by_code.get(code, "Credenciales invalidas."),
                    "details": serializer.errors,
                },
                status=400,
            )
        user = serializer.validated_data["user"]
        membership = serializer.validated_data["membership"]
        return login_response(user, membership, request, amr=serializer.validated_data["amr"])


def login_response(user, membership, request, *, amr):
    refresh, session = issue_tokens(user, membership, request, amr=amr)
    audit(AuditLog.Event.LOGIN_SUCCESS, request=request, user=user, tenant=membership.tenant if membership else None, session_id=session.id)
    return ok(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "session_id": session.id,
            "tenant_id": membership.tenant_id if membership else None,
            "roles": roles_for_membership(membership),
            "permissions": permissions_for_membership(membership),
            "subscription": subscription_summary(membership.tenant) if membership else None,
            "onboarding_required": membership is None,
        }
    )


class MeView(views.APIView):
    @extend_schema(tags=["Auth - Users"], request=None, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        tenant_id = request.auth.get("tenant_id") if request.auth else None
        session_id = request.auth.get("session_id") if request.auth else None
        membership = request.user.memberships.filter(tenant_id=tenant_id).select_related("tenant").first()
        session = UserSession.objects.filter(id=session_id, user=request.user).first()
        return ok(
            {
                "user": UserSerializer(request.user).data,
                "tenant": TenantSerializer(membership.tenant).data if membership else None,
                "membership": TenantMembershipSerializer(membership).data if membership else None,
                "roles": roles_for_membership(membership) if membership else [],
                "permissions": permissions_for_membership(membership) if membership else [],
                "subscription": subscription_summary(membership.tenant) if membership else None,
                "onboarding_required": membership is None,
                "onboarding_completed_at": request.user.profile.onboarding_completed_at,
                "session": {"id": session.id, "status": session.status, "expires_at": session.expires_at} if session else None,
            }
        )


class ProfileView(views.APIView):
    @extend_schema(tags=["Auth - Users"], request=UserProfileUpdateSerializer, responses=UserSerializer)
    def patch(self, request):
        serializer = UserProfileUpdateSerializer(request.user.profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ok(UserSerializer(request.user).data)


class ProfileAvatarView(views.APIView):
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    @extend_schema(tags=["Auth - Users"], request=OpenApiTypes.OBJECT, responses=UserSerializer)
    def post(self, request):
        image = request.FILES.get("image")
        if not image:
            return Response(
                {"success": False, "code": "IMAGE_REQUIRED", "message": "Debes enviar una imagen.", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        stored_path = save_uploaded_image(image, folder=f"profiles/{request.user.id}", max_size=(512, 512))
        request.user.profile.avatar_url = absolute_media_url(request, stored_path)
        request.user.profile.save(update_fields=["avatar_url", "updated_at"])
        return ok(UserSerializer(request.user).data)


class LogoutView(views.APIView):
    @extend_schema(tags=["Auth - Sessions"], request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        session_id = request.auth.get("session_id") if request.auth else None
        UserSession.objects.filter(id=session_id, user=request.user).update(status=UserSession.Status.REVOKED, revoked_at=timezone.now())
        audit(AuditLog.Event.LOGOUT, request=request)
        return ok({"revoked": True})


class LogoutAllView(views.APIView):
    @extend_schema(tags=["Auth - Sessions"], request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        count = UserSession.objects.filter(user=request.user, status=UserSession.Status.ACTIVE).update(status=UserSession.Status.REVOKED, revoked_at=timezone.now())
        audit(AuditLog.Event.SESSION_REVOKED, request=request, revoked=count)
        return ok({"revoked": count})


class ChangePasswordView(views.APIView):
    throttle_scope = "password"

    @extend_schema(tags=["Auth - Password"], request=PasswordChangeSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        UserSession.objects.filter(user=request.user).update(status=UserSession.Status.REVOKED, revoked_at=timezone.now())
        audit(AuditLog.Event.PASSWORD_CHANGED, request=request)
        return ok({"sessions_revoked": True})


class TaggedTokenRefreshView(TokenRefreshView):
    @extend_schema(tags=["Auth - Tokens"])
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        try:
            refresh_claims = FlowkronRefreshToken(request.data.get("refresh") or "")
        except TokenError:
            return Response({"detail": "Token inválido o revocado.", "code": "token_not_valid"}, status=401)

        session_id = refresh_claims.get("session_id")
        session = UserSession.objects.select_for_update().filter(
            id=session_id, user_id=refresh_claims.get("user_id"),
            status=UserSession.Status.ACTIVE, expires_at__gt=timezone.now(),
        ).first()
        membership = None
        if session and refresh_claims.get("membership_id"):
            membership = TenantMembership.objects.select_related("tenant", "user").filter(
                id=refresh_claims["membership_id"], user_id=session.user_id,
                status=TenantMembership.Status.ACTIVE, tenant__status="active",
            ).first()
        if not session or (not membership and not refresh_claims.get("onboarding_required")):
            return Response({"detail": "Tu sesión expiró o se cerró.", "code": "token_not_valid"}, status=401)

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            return Response({"detail": "Token inválido o revocado.", "code": "token_not_valid"}, status=401)
        data = dict(serializer.validated_data)
        session.last_refresh_at = timezone.now()
        session.save(update_fields=["last_refresh_at", "updated_at"])
        access = AccessToken.for_user(session.user)
        access["tenant_id"] = str(membership.tenant_id) if membership else None
        access["membership_id"] = str(membership.id) if membership else None
        access["session_id"] = str(session.id)
        access["roles"] = roles_for_membership(membership)
        access["permissions"] = permissions_for_membership(membership)
        access["subscription"] = subscription_summary(membership.tenant) if membership else None
        access["onboarding_required"] = membership is None
        access["amr"] = refresh_claims.get("amr", "pwd")
        data["access"] = str(access)
        return Response(data, status=status.HTTP_200_OK)


class TaggedTokenVerifyView(TokenVerifyView):
    @extend_schema(tags=["Auth - Tokens"])
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


def _first_error_code(errors):
    if isinstance(errors, dict):
        for value in errors.values():
            code = _first_error_code(value)
            if code:
                return code
    if isinstance(errors, list):
        for value in errors:
            code = _first_error_code(value)
            if code:
                return code
    if isinstance(errors, ErrorDetail):
        return str(errors.code)
    return None
