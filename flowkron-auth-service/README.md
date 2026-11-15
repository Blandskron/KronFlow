# flowkron-auth-service

Microservicio IAM multi-tenant de Flowkron. Gestiona usuarios humanos, tenants y membresías, RBAC, sesiones, JWT RS256, MFA TOTP, service accounts, API keys y auditoría. También coordina el aprovisionamiento del runtime de cada tenant con `flowkron-operational-service`.

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

La lista completa y los flags del entrypoint están en [Despliegue](docs/DEPLOYMENT.md).

## Rutas principales

| Área | Base |
| --- | --- |
| Auth, perfil, MFA, JWKS y M2M | `/api/v1/auth/` |
| Tenants, miembros, invitaciones y runtime | `/api/v1/tenants/` |
| RBAC | `/api/v1/rbac/` |
| Sesiones | `/api/v1/sessions/` |
| Claves y service accounts | `/api/v1/security/` |
| Auditoría | `/api/v1/audit/` |

Consulta el inventario y los requisitos de autorización en [API y contratos](docs/API.md). Swagger es la referencia generada para payloads exactos.

## Flujo humano principal

1. Un administrador crea el usuario. No existe registro publico abierto.
2. El servicio envia un token de verificacion de email. El usuario no puede operar sin `email_verified_at`.
3. El usuario confirma el email en `/api/v1/auth/email/confirm/`; puede incluir `new_password` si necesita definir la password inicial.
4. El usuario inicia sesion en `/api/v1/auth/login/`.
5. Si no tiene tenant activo, el login devuelve `onboarding_required=true` y tokens limitados.
6. El frontend llama `/api/v1/tenants/onboarding/` con el nombre de empresa. El servicio crea tenant, membership activa, rol `TENANT_OWNER`, marca `onboarding_completed_at` y entrega tokens con tenant.
7. Toda operacion tenantizada posterior debe ejecutarse con tenant activo y permisos efectivos.

Las invitaciones no abren registro publico: requieren un token de invitacion valido. Si el email invitado ya existe, el usuario debe iniciar sesion para aceptar. Si no existe, el token permite activar una cuenta nueva con password y asociarla al tenant.

## Validación

```powershell
python -m compileall -q apps config scripts manage.py
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
docker compose config
```

La suite versionada contiene actualmente 20 métodos `test_*`. No confundas ese conteo con una garantía de cobertura completa; las brechas conocidas están en [Testing](docs/TESTING.md).

## Documentación

El índice mantenido está en [docs/README.md](docs/README.md). Las reglas para asistentes de IA están consolidadas en [AGENTS.md](AGENTS.md).

## Propiedad

See the repository license for distribution terms. Consulta [LICENSE](../LICENSE) y [uso aceptable](docs/LEGAL_AND_ACCEPTABLE_USE.md). No incluyas secretos ni credenciales reales en código, ejemplos o documentación.
