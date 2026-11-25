# Despliegue

## Artefactos

- `Dockerfile`
- `.dockerignore`
- `docker-entrypoint.sh`
- `docker-compose.yml`
- `.env.example`

## Imagen Docker

La imagen usa:

```text
python:3.13-slim
```

Incluye:

- dependencias del sistema para PostgreSQL
- dependencias Python desde `requirements.txt`
- Gunicorn
- entrypoint automatizado

## Build

```powershell
docker compose build app
```

## Arranque local completo

```powershell
Copy-Item .env.example .env.local
docker compose --env-file .env.local up --build
```

Servicios:

- `app`
- `postgres`
- `redis`

## Entrypoint

Archivo:

```text
docker-entrypoint.sh
```

Pasos:

1. Espera PostgreSQL si `DATABASE_URL` esta configurado.
2. Crea `AUTH_DATABASE_SCHEMA` si la conexion es PostgreSQL.
3. Genera claves JWT si faltan.
4. Ejecuta migraciones.
5. Ejecuta seeds.
6. Ejecuta collectstatic.
7. Crea el superusuario inicial si `CREATE_SUPERUSER=true`. Si la misma cuenta ya existe y sigue siendo superusuario activo, conserva su contraseña.
8. Ejecuta comando final, por defecto Gunicorn.

## Variables del entrypoint

| Variable | Default | Descripcion |
| --- | --- | --- |
| `GENERATE_JWT_KEYS` | `true` | Genera claves JWT si faltan |
| `RUN_MIGRATIONS` | `true` | Ejecuta `migrate --noinput` |
| `RUN_SEEDS` | `true` | Ejecuta `seed_iam` y `seed_iam_advanced` |
| `RUN_COLLECTSTATIC` | `true` | Ejecuta `collectstatic --noinput` |
| `CREATE_SUPERUSER` | `false` | Crea un superusuario verificado con membresía de propietario en BLANDSKRON |
| `DJANGO_SUPERUSER_EMAIL` | requerido si aplica | Email admin |
| `DJANGO_SUPERUSER_PASSWORD` | requerido si aplica | Password admin |
| `DJANGO_SUPERUSER_USERNAME` | email | Username admin |

## Variables de entorno obligatorias en produccion

```text
DJANGO_SECRET_KEY
DJANGO_DEBUG=False
DATABASE_URL
REDIS_URL
CORS_ALLOWED_ORIGINS
JWT_PRIVATE_KEY_PATH o JWT_PRIVATE_KEY
JWT_PUBLIC_KEY_PATH o JWT_PUBLIC_KEY
SIGNING_KEY_ENCRYPTION_KEY
OPERATIONAL_SERVICE_URL
OPERATIONAL_INTERNAL_TOKEN
APP_PUBLIC_URL
```

Define explícitamente `DJANGO_SETTINGS_MODULE=config.settings.base` en todos los entornos. `DJANGO_DEBUG=False` rechaza el secreto local inseguro, habilita redirect HTTPS/HSTS y fuerza cookies seguras.

El `docker-compose.yml` local del repositorio sobrescribe algunos defaults para desarrollo, incluido `CREATE_SUPERUSER=True` y `GENERATE_JWT_KEYS=True`. En produccion, define esos flags de forma explicita y desactiva `CREATE_SUPERUSER` despues del bootstrap inicial.

## Variables recomendadas

```text
DEFAULT_FROM_EMAIL
EMAIL_BACKEND
MAIL_GATEWAY_URL
MAIL_INTERNAL_API_KEY
MAIL_SENDER_KEY
JWT_PRIVATE_KEY_PATH
JWT_PUBLIC_KEY_PATH
EMAIL_HOST
EMAIL_PORT
EMAIL_HOST_USER
EMAIL_HOST_PASSWORD
EMAIL_USE_TLS
EMAIL_USE_SSL
```

## Gunicorn

Comando por defecto:

```text
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60
```

## Static files

`STATIC_ROOT` apunta a:

```text
staticfiles/
```

WhiteNoise sirve los static files recolectados desde el proceso web. Un CDN o proxy puede agregarse en producción si la escala/política lo requiere.

## Secrets

No incluir en imagen:

- `.env`
- claves JWT productivas
- client secrets
- passwords
- service account secrets
- API keys
- `SIGNING_KEY_ENCRYPTION_KEY`
- `OPERATIONAL_INTERNAL_TOKEN`
- ingest keys

Usar:

- Docker secrets
- Kubernetes secrets
- AWS Secrets Manager
- GCP Secret Manager
- HashiCorp Vault

## Estrategia de despliegue recomendada

1. Build inmutable de imagen.
2. Ejecutar migraciones una sola vez por release.
3. Ejecutar app en replicas horizontales.
4. Mantener claves JWT en volumen o secret manager.
5. Exponer `/api/docs/` solo en ambientes controlados si politica de seguridad lo exige.
6. Monitorear logs JSON y audit events.
7. Sobrescribir el default local de `OPERATIONAL_INTERNAL_TOKEN` y mantener estable `SIGNING_KEY_ENCRYPTION_KEY`.

## Smoke test post deploy

```powershell
docker compose config
docker compose ps
docker compose logs app
```

Validar:

- migraciones aplicadas
- `collectstatic` ejecutado
- superuser creado si corresponde
- `/api/schema/` responde
- `/healthz/` o `/health/` responde (solo liveness)
- `/api/v1/auth/jwks/` responde

See the [transactional email setup](../../README.md#enable-transactional-email) for the HTTP backend. SMTP variables apply to existing deployments using the explicit SMTP backend.
