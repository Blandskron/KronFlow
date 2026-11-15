import secrets
from urllib.parse import urlencode

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError
from rest_framework import parsers, permissions, serializers, views

from apps.audit.models import AuditLog
from apps.audit.services import audit
from apps.security.services import hash_token, verify_totp
from apps.shared.responses import api_error, ok
from apps.tenants.models import Tenant, TenantMembership

from .models import UserProfile
from .views import login_response

User = get_user_model()
GOOGLE_KEYS = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs", timeout=5)
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
GOOGLE_NONCE_SALT = "flowkron.google-login"
GOOGLE_NONCE_MAX_AGE = 900
SIGNUP_SALT = "flowkron.email-signup"
SIGNUP_MAX_AGE = 7200


class PublicAuthView(views.APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    parser_classes = [parsers.JSONParser]


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=150)


class SignupCompleteSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=2048, write_only=True)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


class GoogleLoginSerializer(serializers.Serializer):
    credential = serializers.CharField(max_length=8192, write_only=True)
    nonce = serializers.CharField(max_length=256, write_only=True)
    mfa_code = serializers.RegexField(r"^[0-9]{6}$", required=False, write_only=True)


class AuthOptionsView(PublicAuthView):
    @extend_schema(tags=["Auth - Users"], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        nonce = signing.dumps(secrets.token_urlsafe(24), salt=GOOGLE_NONCE_SALT) if client_id else ""
        response = ok({"signup_enabled": settings.AUTH_SELF_SIGNUP_ENABLED, "google_client_id": client_id, "google_nonce": nonce})
        response["Cache-Control"] = "no-store"
        return response


def find_user_by_email(email):
    return User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists()


def create_verified_user(*, email, password=None, google_subject=None):
    with transaction.atomic():
        user = User(username=email, email=email)
        user.set_password(password)
        user._skip_email_verification = True
        user.save(force_insert=True)
        now = timezone.now()
        UserProfile.objects.filter(user=user).update(
            email_verified_at=now,
            account_activated_at=now,
            initial_password_set_at=now if password else None,
            google_subject=google_subject,
        )
        audit(AuditLog.Event.USER_CREATED, user=user, method="google" if google_subject else "email")
    return user


def signup_disabled():
    return api_error(status=403, error_code="SIGNUP_DISABLED", detail="El registro está deshabilitado en esta instancia.")


class SignupView(PublicAuthView):
    throttle_scope = "password"

    @extend_schema(tags=["Auth - Users"], request=SignupSerializer, responses={202: OpenApiTypes.OBJECT})
    def post(self, request):
        if not settings.AUTH_SELF_SIGNUP_ENABLED:
            return signup_disabled()
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        if not find_user_by_email(email) and cache.add(f"signup-email:{hash_token(email)}", True, timeout=90):
            token = signing.dumps(email, salt=SIGNUP_SALT)
            # Keep the token out of HTTP request URLs and proxy access logs.
            confirm_url = f"{settings.APP_PUBLIC_URL.rstrip('/')}/registrarse#{urlencode({'token': token})}"
            try:
                send_mail(
                    "Crea tu cuenta de Flowkron",
                    f"Para confirmar tu correo y elegir tu contraseña, abre este enlace:\n\n{confirm_url}\n\n"
                    "El enlace vence en dos horas. Si no solicitaste una cuenta, puedes ignorar este mensaje.",
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                )
            except Exception:
                cache.delete(f"signup-email:{hash_token(email)}")
                return api_error(status=503, error_code="SIGNUP_MAIL_UNAVAILABLE", detail="No pudimos enviar el correo. Intenta más tarde.")
        return ok({"accepted": True}, status=202)


class SignupCompleteView(PublicAuthView):
    throttle_scope = "password"

    @extend_schema(tags=["Auth - Users"], request=SignupCompleteSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        if not settings.AUTH_SELF_SIGNUP_ENABLED:
            return signup_disabled()
        serializer = SignupCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            email = signing.loads(serializer.validated_data["token"], salt=SIGNUP_SALT, max_age=SIGNUP_MAX_AGE)
        except signing.BadSignature:
            return api_error(error_code="SIGNUP_LINK_INVALID", detail="El enlace venció o es inválido. Solicita otro correo.")

        if find_user_by_email(email):
            return api_error(status=409, error_code="SIGNUP_UNAVAILABLE", detail="El enlace ya no está disponible. Inicia sesión o recupera tu contraseña.")
        password = serializer.validated_data["password"]
        try:
            validate_password(password, User(username=email, email=email))
        except ValidationError as exc:
            return api_error(error_code="SIGNUP_PASSWORD_INVALID", detail=" ".join(exc.messages))
        try:
            create_verified_user(email=email, password=password)
        except IntegrityError:
            if not find_user_by_email(email):
                raise
            return api_error(status=409, error_code="SIGNUP_UNAVAILABLE", detail="El enlace ya no está disponible. Inicia sesión o recupera tu contraseña.")
        return ok({"created": True}, status=201)


def verify_google_credential(credential, nonce):
    signing.loads(nonce, salt=GOOGLE_NONCE_SALT, max_age=GOOGLE_NONCE_MAX_AGE)
    key = GOOGLE_KEYS.get_signing_key_from_jwt(credential)
    claims = jwt.decode(
        credential,
        key.key,
        algorithms=["RS256"],
        audience=settings.GOOGLE_OAUTH_CLIENT_ID,
        issuer=GOOGLE_ISSUERS,
        options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
    )
    if claims["nonce"] != nonce or claims.get("azp", settings.GOOGLE_OAUTH_CLIENT_ID) != settings.GOOGLE_OAUTH_CLIENT_ID:
        raise jwt.InvalidTokenError("Google challenge mismatch")
    return claims


def google_identity(claims):
    subject, email = claims.get("sub"), claims.get("email")
    if not isinstance(subject, str) or not 0 < len(subject) <= 255:
        raise jwt.InvalidTokenError("Invalid subject")
    if claims.get("email_verified") is not True or not isinstance(email, str):
        raise jwt.InvalidTokenError("Unverified Google email")
    email = serializers.EmailField(max_length=150).run_validation(email).lower()
    return subject, email


class GoogleLoginView(PublicAuthView):
    throttle_scope = "login"

    @extend_schema(tags=["Auth - Users"], request=GoogleLoginSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        if not settings.GOOGLE_OAUTH_CLIENT_ID:
            return api_error(status=404, error_code="GOOGLE_DISABLED", detail="El acceso con Google no está habilitado.")
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        nonce = data["nonce"]
        try:
            claims = verify_google_credential(data["credential"], nonce)
            subject, email = google_identity(claims)
        except PyJWKClientConnectionError:
            return api_error(status=503, error_code="GOOGLE_UNAVAILABLE", detail="Google no está disponible. Intenta más tarde.")
        except (signing.BadSignature, PyJWTError, serializers.ValidationError):
            return api_error(error_code="GOOGLE_INVALID", detail="No se pudo verificar el acceso con Google. Vuelve a intentarlo.")

        profile = UserProfile.objects.select_related("user").filter(google_subject=subject).first()
        if profile:
            if not profile.user.is_active or not profile.email_verified_at:
                return api_error(status=403, error_code="AUTH_USER_INACTIVE", detail="La cuenta de Flowkron no está activa.")
            if profile.mfa_enabled and not verify_totp(profile.user, data.get("mfa_code", "")):
                return api_error(error_code="MFA_REQUIRED", detail="Ingresa un código de autenticación válido.")
        else:
            if not settings.AUTH_SELF_SIGNUP_ENABLED:
                return signup_disabled()
            if find_user_by_email(email):
                return api_error(status=409, error_code="GOOGLE_ACCOUNT_EXISTS", detail="Esta dirección ya tiene una cuenta en Flowkron. Entra con tu contraseña.")
            if not email.endswith("@gmail.com") and not claims.get("hd"):
                return api_error(status=403, error_code="GOOGLE_EMAIL_NOT_AUTHORITATIVE", detail="Para esta dirección, crea una cuenta de Flowkron mediante verificación por correo.")

        if not cache.add(f"google-login:{hash_token(nonce)}", True, timeout=GOOGLE_NONCE_MAX_AGE):
            return api_error(error_code="GOOGLE_REPLAY", detail="Este intento ya se usó. Vuelve a abrir el botón de Google.")

        if profile:
            user = profile.user
        else:
            try:
                user = create_verified_user(email=email, google_subject=subject)
            except IntegrityError:
                # A concurrent request may have created this identity. Require a fresh login.
                if not find_user_by_email(email) and not UserProfile.objects.filter(google_subject=subject).exists():
                    raise
                return api_error(status=409, error_code="GOOGLE_SIGNUP_CONFLICT", detail="La cuenta cambió durante el acceso. Vuelve a iniciar sesión.")

        membership = user.memberships.filter(status=TenantMembership.Status.ACTIVE, tenant__status=Tenant.Status.ACTIVE).first()
        return login_response(user, membership, request, amr="mfa" if profile and profile.mfa_enabled else "google")
