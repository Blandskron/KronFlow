from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ErrorDetail
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import parsers, permissions, status, views
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenBackendError, TokenError
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from apps.audit.models import AuditLog
from apps.audit.services import audit
from apps.rbac.services import permissions_for_membership, roles_for_membership
from apps.sessions.models import UserSession
from apps.sessions.revocation import revoke_jti, revoke_session, revoke_user_tokens
from apps.sessions.services import mark_refresh_reuse
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


REFRESH_COOKIE_NAME = "flowkron_refresh"


def _set_refresh_cookie(resp, refresh_token: str) -> None:
    if not getattr(settings, "AUTH_REFRESH_COOKIE_ENABLED", False):
        return
    resp.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=14 * 24 * 3600,
        httponly=True,
        secure=not getattr(settings, "DEBUG", False),
        samesite="Lax",
        path="/api/v1/auth/",
    )


def _clear_refresh_cookie(resp) -> None:
    if not getattr(settings, "AUTH_REFRESH_COOKIE_ENABLED", False):
        return
    resp.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/v1/auth/", samesite="Lax")


def login_response(user, membership, request, *, amr):
    refresh, session = issue_tokens(user, membership, request, amr=amr)
    audit(AuditLog.Event.LOGIN_SUCCESS, request=request, user=user, tenant=membership.tenant if membership else None, session_id=session.id)
    resp = ok(
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
    _set_refresh_cookie(resp, str(refresh))
    return resp


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


class MeExportView(views.APIView):
    """GDPR Art. 15/20 & Ley 21.719 Art. 5/9 portable DSAR export for the authenticated IAM user (PRV-015)."""

    @extend_schema(tags=["Auth - Users"], request=None, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        user = request.user
        memberships = list(
            user.memberships.select_related("tenant").prefetch_related("membership_roles__role").all()
        )
        sessions = list(
            UserSession.objects.filter(user=user)
            .order_by("-created_at")
            .values("id", "tenant_id", "status", "ip_address", "user_agent", "created_at", "expires_at", "revoked_at")
        )
        audit_events = list(
            AuditLog.objects.filter(user=user)
            .order_by("-created_at")[:200]
            .values("id", "event", "tenant_id", "created_at")
        )
        return ok(
            {
                "exported_at": timezone.now().isoformat(),
                "user": UserSerializer(user).data,
                "memberships": TenantMembershipSerializer(memberships, many=True).data,
                "sessions": sessions,
                "audit_events": audit_events,
            }
        )


class MeEraseView(views.APIView):
    """GDPR Art. 17 & Ley 21.719 Art. 7 IAM account erasure/anonymization protecting last active owner (PRV-015)."""

    @extend_schema(tags=["Auth - Users"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def post(self, request):
        if request.data.get("confirmed") is not True:
            return Response(
                {
                    "success": False,
                    "code": "ERASURE_CONFIRMATION_REQUIRED",
                    "message": "Debes confirmar explicitamente la eliminacion de tu cuenta.",
                    "details": {},
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        user = User.objects.select_for_update().get(pk=request.user.pk)
        owned_memberships = list(
            TenantMembership.objects.select_related("tenant").filter(
                user=user,
                status=TenantMembership.Status.ACTIVE,
                tenant__status="active",
                membership_roles__role__code="TENANT_OWNER",
            ).distinct()
        )
        for mem in owned_memberships:
            other_owners = TenantMembership.objects.filter(
                tenant=mem.tenant,
                status=TenantMembership.Status.ACTIVE,
                membership_roles__role__code="TENANT_OWNER",
            ).exclude(user=user).distinct().count()
            if other_owners == 0:
                return Response(
                    {
                        "success": False,
                        "code": "LAST_OWNER_ERASURE_DENIED",
                        "message": "No puedes eliminar tu cuenta mientras seas el unico propietario activo de un tenant.",
                        "details": {"tenant_id": mem.tenant_id},
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        now = timezone.now()
        user.email = f"anon-{user.id}@erased.invalid"
        user.username = f"anon-{user.id}"
        user.first_name = ""
        user.last_name = ""
        user.is_active = False
        user.set_unusable_password()
        user.save(update_fields=["email", "username", "first_name", "last_name", "is_active", "password"])

        profile = getattr(user, "profile", None)
        if profile is not None:
            profile.display_name = "Anonimizado"
            profile.phone = ""
            profile.avatar_url = ""
            profile.google_subject = None
            profile.mfa_enabled = False
            profile.save(update_fields=["display_name", "phone", "avatar_url", "google_subject", "mfa_enabled", "updated_at"])

        from apps.security.models import MfaDevice, MfaRecoveryCode

        MfaDevice.objects.filter(user=user).delete()
        MfaRecoveryCode.objects.filter(user=user).delete()

        TenantMembership.objects.filter(user=user, status=TenantMembership.Status.ACTIVE).update(
            status=TenantMembership.Status.REVOKED,
            revoked_at=now,
        )
        revoked_sessions = UserSession.objects.filter(user=user, status=UserSession.Status.ACTIVE).update(
            status=UserSession.Status.REVOKED,
            revoked_at=now,
        )
        revoke_user_tokens(user.id)
        audit(AuditLog.Event.SESSION_REVOKED, request=request, user=user, reason="iam_user_erasure", revoked=revoked_sessions)

        resp = ok({"erased": True, "user_id": user.id, "sessions_revoked": revoked_sessions})
        _clear_refresh_cookie(resp)
        return resp


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
        jti = request.auth.get("jti") if request.auth else None
        UserSession.objects.filter(id=session_id, user=request.user).update(status=UserSession.Status.REVOKED, revoked_at=timezone.now())
        revoke_session(session_id)
        revoke_jti(jti)
        audit(AuditLog.Event.LOGOUT, request=request)
        resp = ok({"revoked": True})
        _clear_refresh_cookie(resp)
        return resp


class LogoutAllView(views.APIView):
    @extend_schema(tags=["Auth - Sessions"], request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        count = UserSession.objects.filter(user=request.user, status=UserSession.Status.ACTIVE).update(status=UserSession.Status.REVOKED, revoked_at=timezone.now())
        revoke_user_tokens(request.user.id)
        audit(AuditLog.Event.SESSION_REVOKED, request=request, revoked=count)
        resp = ok({"revoked": count})
        _clear_refresh_cookie(resp)
        return resp


class ChangePasswordView(views.APIView):
    throttle_scope = "password"

    @extend_schema(tags=["Auth - Password"], request=PasswordChangeSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        UserSession.objects.filter(user=request.user).update(status=UserSession.Status.REVOKED, revoked_at=timezone.now())
        revoke_user_tokens(request.user.id)
        audit(AuditLog.Event.PASSWORD_CHANGED, request=request)
        return ok({"sessions_revoked": True})


def _handle_possible_refresh_reuse(raw_token, request) -> None:
    if not isinstance(raw_token, str) or not raw_token:
        return
    try:
        decoded = token_backend.decode(raw_token, verify=True)
    except TokenBackendError:
        return
    if decoded.get("token_type") != "refresh":
        return
    jti = decoded.get("jti")
    session_id = decoded.get("session_id")
    user_id = decoded.get("user_id")
    if not jti or not session_id or not user_id:
        return
    if not BlacklistedToken.objects.filter(token__jti=jti).exists():
        return
    session = UserSession.objects.select_for_update().filter(
        id=session_id,
        user_id=user_id,
        status=UserSession.Status.ACTIVE,
    ).first()
    if session is not None:
        mark_refresh_reuse(session, request=request)


class TaggedTokenRefreshView(TokenRefreshView):
    @extend_schema(tags=["Auth - Tokens"])
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        raw_refresh = request.data.get("refresh") or request.COOKIES.get(REFRESH_COOKIE_NAME) or ""
        try:
            refresh_claims = FlowkronRefreshToken(raw_refresh)
        except TokenError:
            _handle_possible_refresh_reuse(raw_refresh, request)
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

        serializer = self.get_serializer(data={"refresh": raw_refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            _handle_possible_refresh_reuse(raw_refresh, request)
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
        resp = Response(data, status=status.HTTP_200_OK)
        if data.get("refresh"):
            _set_refresh_cookie(resp, str(data["refresh"]))
        return resp


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
