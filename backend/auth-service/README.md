# KronFlow Auth Service (`backend/auth-service`)

Microservicio IAM multi-tenant de **KronFlow — Intelligent CRM** (*By BLANDSKRON*). Gestiona usuarios humanos, registro y verificación por correo, Google Identity Services, tenants y membresías, RBAC, sesiones, JWT RS256, MFA TOTP, service accounts, API keys y auditoría. También coordina el aprovisionamiento del runtime de cada tenant con `operational-service`.

## Capacidades implementadas

- Creación manual de usuarios, verificación de correo, activación de cuenta, login, refresh, logout y recuperación de contraseña.
- Perfil y avatar de usuario; logo de tenant.
- Onboarding obligatorio de empresa para usuarios sin tenant, invitaciones, membresías y planes `free`, `starter`, `pro`, `enterprise`.
- Permisos efectivos como intersección de RBAC y entitlements del plan.
- Sesiones con revocación y señales básicas de riesgo por IP/dispositivo.
- MFA TOTP, JWKS y rotación de claves de firma.
- Credenciales de máquina y API keys administrativas por tenant.
- Aprovisionamiento y rotación de ingest key en el servicio operacional.
- OpenAPI/Swagger, healthcheck y logs JSON con IDs de correlación.

Límites importantes: este servicio no autentica requests mediante `Authorization: ApiKey`; solo administra esas claves. Tampoco contiene los datos operacionales schema-per-tenant: estos viven en el servicio operacional.

## Stack

Python 3.13, Django 5, Django REST Framework, PostgreSQL, Redis, Simple JWT, Celery, django-axes, drf-spectacular, Argon2, Gunicorn y Docker Compose.

## Inicio local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts/generate_jwt_keys.py
python manage.py migrate
python manage.py seed_iam
python manage.py seed_iam_advanced
python manage.py runserver
```

Antes de iniciar Django directamente, sustituye todos los valores `replace-with-*` de `.env`. Para Docker, usa `.env.local` porque `docker-compose.yml` lo declara como `env_file`:

```powershell
Copy-Item .env.example .env.local
docker compose --env-file .env.local up --build
```

El Compose levanta `app`, `postgres` y `redis`. No incluye credenciales funcionales por defecto: el correo y la contraseña del superusuario deben configurarse en `.env.local`.

## URLs locales

- API: `http://127.0.0.1:8000/api/v1/`
- Healthcheck liveness: `http://127.0.0.1:8000/health/` y `http://127.0.0.1:8000/healthz/`
- OpenAPI: `http://127.0.0.1:8000/api/schema/`
- Swagger UI: `http://127.0.0.1:8000/api/docs/`
- Admin: `http://127.0.0.1:8000/admin/`

## Configuración esencial

| Variable | Propósito |
| --- | --- |
| `DJANGO_SECRET_KEY` | Secreto de Django; obligatorio y no trivial en producción |
| `DJANGO_DEBUG` | Activa debug local |
| `DATABASE_URL` | Base de datos; SQLite es solo el fallback local sin Docker |
| `REDIS_URL` | Cache y broker/result backend de Celery |
| `CORS_ALLOWED_ORIGINS` | Orígenes frontend permitidos |
| `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` | Par RS256 de Simple JWT |
| `SIGNING_KEY_ENCRYPTION_KEY` | Protege claves privadas administradas en base de datos |
| `OPERATIONAL_SERVICE_URL` | Base URL del servicio operacional |
| `OPERATIONAL_INTERNAL_TOKEN` | Credencial para sus endpoints internos |
| `APP_PUBLIC_URL` | Base URL usada en enlaces de invitación |
| `EMAIL_*` / `DEFAULT_FROM_EMAIL` | SMTP y remitente |

La lista completa de variables vive en `.env.example` y `config/settings.py`.

## Rutas principales

| Área | Base |
| --- | --- |
| Auth, perfil, MFA, JWKS y M2M | `/api/v1/auth/` |
| Tenants, miembros, invitaciones y runtime | `/api/v1/tenants/` |
| RBAC | `/api/v1/rbac/` |
| Sesiones | `/api/v1/sessions/` |
| Claves y service accounts | `/api/v1/security/` |
| Auditoría | `/api/v1/audit/` |

Swagger (`/api/docs/`) y el esquema OpenAPI (`/api/schema/`) son la referencia viva para payloads y requisitos de autorización.

## Flujo humano principal

1. El usuario se registra mediante self-signup (`AUTH_SELF_SIGNUP_ENABLED=True`), Google Sign-In o invitación de administrador.
2. Para registro por correo, el servicio envía un token de verificación (ver [email](../../README.md#correo-transaccional)). El usuario confirma su correo en `/api/v1/auth/email/confirm/`.
3. El usuario inicia sesión en `/api/v1/auth/login/` o `/api/v1/auth/google/`.
4. Si no tiene tenant activo, el login devuelve `onboarding_required=true` y tokens limitados.
5. El frontend llama `/api/v1/tenants/onboarding/` con el nombre de empresa; el servicio crea el tenant, membresía `TENANT_OWNER`, aprovisiona el runtime operacional y entrega tokens con `tenant_id`.
6. Toda operación tenantizada posterior se ejecuta con tenant activo y permisos efectivos.

Las invitaciones requieren un token válido: si el email ya existe, el usuario inicia sesión para aceptar; si no existe, activa su cuenta y se asocia al tenant.

## Validación

```powershell
ruff check --select E9,F63,F7,F82 .
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
docker compose config --quiet
```

## Protocolo y licencia

Las reglas agénticas y de validación del monorepo están consolidadas en [AGENTS.md](../../AGENTS.md) y [.agents/skills/backend-multitenant/SKILL.md](../../.agents/skills/backend-multitenant/SKILL.md). Distribuido bajo [Apache License 2.0](../../LICENSE). No incluyas secretos ni credenciales reales en código, ejemplos o documentación.
