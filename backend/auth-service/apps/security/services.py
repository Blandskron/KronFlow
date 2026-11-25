import base64
import hashlib
import json
import logging
import secrets
from datetime import timedelta
from hmac import compare_digest
from urllib.parse import quote

import jwt
import pyotp
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.core.signing import BadSignature, Signer
from django.template.loader import render_to_string
from django.utils import timezone
from jwt.algorithms import RSAAlgorithm
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.audit.models import AuditLog
from apps.audit.services import audit
from apps.sessions.models import UserSession

from .models import APIKey, EmailVerificationToken, MfaDevice, MfaRecoveryCode, PasswordResetToken, ServiceAccount, SigningKey

MACHINE_SCOPES = ["auth.verify_token", "users.read", "sessions.validate", "tenants.read"]
logger = logging.getLogger(__name__)


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def hash_secret(secret):
    return hash_token(secret)


def _fernet():
    source = getattr(settings, "SIGNING_KEY_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=settings.SIGNING_KEY_ENCRYPTION_SALT.encode(), info=b"signing-key-encryption").derive(source.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_private_key(private_key):
    return _fernet().encrypt(private_key.encode()).decode()


def decrypt_private_key(encrypted_private_key):
    try:
        return _fernet().decrypt(encrypted_private_key.encode()).decode()
    except InvalidToken:
        try:
            return base64.b64decode(Signer().unsign(encrypted_private_key)).decode()
        except BadSignature as exc:
            raise ValueError("Private key signature invalid") from exc
    except BadSignature as exc:
        raise ValueError("Private key signature invalid") from exc


def generate_rsa_key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_bytes.decode(), public_bytes.decode()


def create_signing_key(kid=None, expires_at=None):
    private_key, public_key = generate_rsa_key_pair()
    kid = kid or f"flowkron-{timezone.now():%Y%m%d%H%M%S}-{secrets.token_hex(4)}"
    return SigningKey.objects.create(
        kid=kid,
        public_key=public_key,
        encrypted_private_key=encrypt_private_key(private_key),
        expires_at=expires_at or timezone.now() + timedelta(days=180),
    )


def get_active_signing_key():
    key = SigningKey.objects.filter(status=SigningKey.Status.ACTIVE, expires_at__gt=timezone.now()).order_by("-created_at").first()
    if key:
        return key
    return create_signing_key()


def rotate_signing_key(request=None, compatibility_days=14):
    now = timezone.now()
    SigningKey.objects.filter(status=SigningKey.Status.ACTIVE).update(status=SigningKey.Status.INACTIVE, rotated_at=now, expires_at=now + timedelta(days=compatibility_days))
    key = create_signing_key()
    audit(AuditLog.Event.SIGNING_KEY_ROTATED, request=request, kid=key.kid, compatibility_days=compatibility_days)
    return key


def jwks_payload():
    keys = []
    qs = SigningKey.objects.exclude(status=SigningKey.Status.REVOKED).filter(expires_at__gt=timezone.now())
    for signing_key in qs.order_by("-created_at"):
        public_key = serialization.load_pem_public_key(signing_key.public_key.encode())
        payload = json.loads(RSAAlgorithm.to_jwk(public_key))
        payload.update({"kid": signing_key.kid, "alg": signing_key.algorithm, "use": "sig"})
        keys.append(payload)
    return {"keys": keys}


def create_service_account(name, scopes=None, expires_at=None, request=None):
    client_secret = secrets.token_urlsafe(40)
    account = ServiceAccount.objects.create(
        name=name,
        client_id=f"svc_{secrets.token_urlsafe(18)}",
        secret_hash=hash_secret(client_secret),
        scopes=scopes or MACHINE_SCOPES,
        expires_at=expires_at,
    )
    account.plain_client_secret = client_secret
    audit(AuditLog.Event.SERVICE_ACCOUNT_CREATED, request=request, service_account=account.client_id)
    return account


def issue_client_credentials_token(client_id, client_secret, requested_scopes=None):
    account = ServiceAccount.objects.get(client_id=client_id, status=ServiceAccount.Status.ACTIVE)
    if account.expires_at and account.expires_at < timezone.now():
        raise ValueError("Service account expired")
    if not compare_digest(account.secret_hash, hash_secret(client_secret)):
        raise ValueError("Invalid client credentials")
    scopes = requested_scopes or account.scopes
    if not set(scopes).issubset(set(account.scopes)):
        raise ValueError("Requested scope not allowed")
    signing_key = get_active_signing_key()
    now = timezone.now()
    payload = {
        "iss": settings.SIMPLE_JWT["ISSUER"],
        "aud": settings.SIMPLE_JWT["AUDIENCE"],
        "sub": account.client_id,
        "typ": "service_account",
        "scopes": scopes,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    token = jwt.encode(payload, decrypt_private_key(signing_key.encrypted_private_key), algorithm=signing_key.algorithm, headers={"kid": signing_key.kid})
    account.last_used_at = now
    account.save(update_fields=["last_used_at", "updated_at"])
    return token


def create_api_key(tenant, name, scopes, created_by=None, expires_at=None, request=None):
    plain_key = f"flowkron_{secrets.token_urlsafe(32)}"
    api_key = APIKey.objects.create(
        tenant=tenant,
        name=name,
        prefix=plain_key[:12],
        key_hash=hash_secret(plain_key),
        scopes=scopes,
        expires_at=expires_at,
        created_by=created_by,
    )
    api_key.plain_key = plain_key
    audit(AuditLog.Event.API_KEY_CREATED, request=request, tenant=tenant, api_key=api_key.id)
    return api_key


def rotate_api_key(api_key, request=None):
    api_key.status = APIKey.Status.REVOKED
    api_key.revoked_at = timezone.now()
    api_key.save(update_fields=["status", "revoked_at", "updated_at"])
    replacement = create_api_key(api_key.tenant, api_key.name, api_key.scopes, api_key.created_by, api_key.expires_at, request)
    audit(AuditLog.Event.API_KEY_ROTATED, request=request, tenant=api_key.tenant, old_api_key=api_key.id, new_api_key=replacement.id)
    return replacement


def introspect_token(raw_token):
    if not raw_token:
        return {"active": False}
    unverified = jwt.get_unverified_header(raw_token)
    kid = unverified.get("kid")
    signing_key = SigningKey.objects.filter(kid=kid).exclude(status=SigningKey.Status.REVOKED).first()
    if signing_key:
        payload = jwt.decode(raw_token, signing_key.public_key, algorithms=[signing_key.algorithm], audience=settings.SIMPLE_JWT["AUDIENCE"], issuer=settings.SIMPLE_JWT["ISSUER"])
    else:
        payload = jwt.decode(
            raw_token,
            settings.SIMPLE_JWT.get("VERIFYING_KEY", ""),
            algorithms=[settings.SIMPLE_JWT.get("ALGORITHM", "RS256")],
            audience=settings.SIMPLE_JWT["AUDIENCE"],
            issuer=settings.SIMPLE_JWT["ISSUER"],
        )
    session_id = payload.get("session_id")
    if session_id:
        session = UserSession.objects.filter(id=session_id).first()
        if not session or not session.is_active:
            return {"active": False, "reason": "session_inactive"}
    return {"active": True, "claims": payload}


def create_email_token(user):
    token = secrets.token_urlsafe(32)
    EmailVerificationToken.objects.create(user=user, token_hash=hash_token(token), expires_at=timezone.now() + timezone.timedelta(hours=2))
    return token


def create_password_reset_token(user):
    token = f"{secrets.randbelow(1000):03d}-{secrets.randbelow(1000):03d}"
    PasswordResetToken.objects.create(user=user, token_hash=hash_token(token), expires_at=timezone.now() + timezone.timedelta(minutes=30))
    return token


def send_verification_email(user):
    token = create_email_token(user)
    confirm_url = f"{settings.APP_PUBLIC_URL.rstrip('/')}/confirm-email?token={quote(token)}"
    context = {
        "confirm_url": confirm_url,
        "token": token,
        "user_email": user.email,
        "app_name": "Flowkron",
    }
    text_body = render_to_string("emails/email_verification.txt", context)
    html_body = render_to_string("emails/email_verification.html", context)
    try:
        email = EmailMultiAlternatives(
            "Verifica tu correo Flowkron",
            text_body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
    except Exception:
        logger.exception("No se pudo enviar email de verificacion a %s", user.email)
        if getattr(settings, "EMAIL_LOG_TOKEN_ON_FAILURE", False):
            logger.warning("Token de verificacion generado para entrega manual a %s: %s", user.email, token)
        return False
    audit(AuditLog.Event.EMAIL_VERIFICATION_SENT, user=user)
    return True


def send_password_reset_email(user):
    token = create_password_reset_token(user)
    try:
        send_mail(
            "Recupera tu password Flowkron",
            f"Tu codigo de recuperacion es: {token}\n\nEste codigo vence en 30 minutos.",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("No se pudo enviar email de recuperacion a %s", user.email)
        if getattr(settings, "EMAIL_LOG_TOKEN_ON_FAILURE", False):
            logger.warning("Token de recuperacion generado para entrega manual a %s: %s", user.email, token)
        return False
    audit(AuditLog.Event.PASSWORD_RESET_REQUESTED, user=user)
    return True


def setup_totp(user):
    secret = pyotp.random_base32()
    device, _ = MfaDevice.objects.update_or_create(user=user, defaults={"secret": secret, "confirmed_at": None})
    uri = pyotp.TOTP(device.secret).provisioning_uri(name=user.email, issuer_name="Flowkron")
    return device, uri


def verify_totp(user, code):
    device = getattr(user, "mfa_device", None)
    if not device:
        return False
    return pyotp.TOTP(device.secret).verify(code, valid_window=1)


def generate_recovery_codes(user, count=10):
    MfaRecoveryCode.objects.filter(user=user, used_at__isnull=True).delete()
    plain_codes = []
    for _ in range(count):
        code = base64.b32encode(secrets.token_bytes(5)).decode().rstrip("=")
        plain_codes.append(code)
        MfaRecoveryCode.objects.create(user=user, code_hash=hash_token(code))
    return plain_codes
