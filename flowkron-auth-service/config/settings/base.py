import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import environ
from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent
env = environ.FileAwareEnv(
    DJANGO_DEBUG=(bool, True),
    CORS_ALLOWED_ORIGINS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-local-dev-key")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
if not DEBUG and SECRET_KEY == "unsafe-local-dev-key":
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG=False.")
IAM_AUTO_VERIFY_USER_EMAIL = env.bool("IAM_AUTO_VERIFY_USER_EMAIL", default=False)

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    "axes",
]

LOCAL_APPS = [
    "apps.shared",
    "apps.accounts",
    "apps.contact",
    "apps.tenants",
    "apps.rbac",
    "apps.sessions",
    "apps.audit",
    "apps.security",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.shared.middleware.CorrelationIdMiddleware",
    "apps.shared.middleware.ApiContractMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

AUTH_DATABASE_SCHEMA = env("AUTH_DATABASE_SCHEMA", default="auth_")
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", AUTH_DATABASE_SCHEMA):
    raise ValueError("AUTH_DATABASE_SCHEMA must be a valid PostgreSQL identifier.")

DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}
if DATABASES["default"]["ENGINE"].endswith("postgresql"):
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"]["options"] = f"-c search_path={AUTH_DATABASE_SCHEMA},public"

def valid_redis_url(value: str) -> str:
    candidate = value.strip()
    if not candidate or "${{" in candidate or "}}" in candidate:
        return ""
    parsed = urlparse(candidate)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        return ""
    return candidate


REDIS_URL = valid_redis_url(env("REDIS_URL", default=""))
CACHES = (
    {"default": env.cache("REDIS_URL")}
    if REDIS_URL
    else {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "flowkron-auth",
        }
    }
)

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SITE_ID = 1

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-correlation-id",
    "x-csrftoken",
    "x-tenant-id",
]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "apps.shared.exceptions.csrf_failure"
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not DEBUG)
SECURE_REDIRECT_EXEMPT = [r"^health/$", r"^healthz/$"]
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000 if not DEBUG else 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "login": "10/minute",
        "password": "5/minute",
        "mfa": "10/minute",
        "machine": "20/minute",
        "contact": "5/minute",
    },
    "EXCEPTION_HANDLER": "apps.shared.exceptions.standard_exception_handler",
}

JWT_PRIVATE_KEY = ""
JWT_PUBLIC_KEY = ""
private_key_path = env("JWT_PRIVATE_KEY_PATH", default="")
public_key_path = env("JWT_PUBLIC_KEY_PATH", default="")
if private_key_path and (BASE_DIR / private_key_path).exists():
    JWT_PRIVATE_KEY = (BASE_DIR / private_key_path).read_text()
if public_key_path and (BASE_DIR / public_key_path).exists():
    JWT_PUBLIC_KEY = (BASE_DIR / public_key_path).read_text()

SIMPLE_JWT = {
    "ALGORITHM": "RS256",
    "SIGNING_KEY": env("JWT_PRIVATE_KEY", default=JWT_PRIVATE_KEY),
    "VERIFYING_KEY": env("JWT_PUBLIC_KEY", default=JWT_PUBLIC_KEY),
    "AUDIENCE": env("JWT_AUDIENCE", default="flowkron"),
    "ISSUER": env("JWT_ISSUER", default="flowkron-auth-service"),
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Flowkron IAM API",
    "DESCRIPTION": "Autenticacion, tenants, RBAC, sesiones, MFA y auditoria.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

IAM_PLATFORM_TENANT_SLUG = env("IAM_PLATFORM_TENANT_SLUG", default="flowkron-platform")
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
OPERATIONAL_SERVICE_URL = env("OPERATIONAL_SERVICE_URL", default="http://localhost:8001")
OPERATIONAL_INTERNAL_TOKEN = env("OPERATIONAL_INTERNAL_TOKEN", default="change-me-local-internal-token")
APP_PUBLIC_URL = env("APP_PUBLIC_URL", default="http://localhost:8081")
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID", default="").strip()
AUTH_SELF_SIGNUP_ENABLED = env.bool("AUTH_SELF_SIGNUP_ENABLED", default=True)
SIGNING_KEY_ENCRYPTION_KEY = env("SIGNING_KEY_ENCRYPTION_KEY", default="")
SIGNING_KEY_ENCRYPTION_SALT = env("SIGNING_KEY_ENCRYPTION_SALT", default="flowkron-auth-service")
MAIL_GATEWAY_URL = env("MAIL_GATEWAY_URL", default="")
MAIL_INTERNAL_API_KEY = env("MAIL_INTERNAL_API_KEY", default="")
MAIL_SENDER_KEY = env("MAIL_SENDER_KEY", default="flowkron")
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default=(
        "apps.shared.email_backend.EmailGatewayBackend"
        if MAIL_GATEWAY_URL
        else "django.core.mail.backends.smtp.EmailBackend"
    ),
)
EMAIL_HOST = env("EMAIL_HOST", default="mail.blandskron.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=465)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=True)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=EMAIL_HOST_USER or "no-reply@flowkron.example")
EMAIL_LOG_TOKEN_ON_FAILURE = env.bool("EMAIL_LOG_TOKEN_ON_FAILURE", default=False)

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]

CELERY_BROKER_URL = REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = REDIS_URL or "cache+memory://"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "apps.shared.logging.JsonFormatter",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
