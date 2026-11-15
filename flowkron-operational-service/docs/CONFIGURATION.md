# Configuración y despliegue

Este microservicio usa `flowkron-operational-service/.env.local` para Docker local. `.env.example` es la plantilla versionable y debe mantenerse sincronizada con `app/core/config.py`. El `.env` puede quedar reservado para Railway.

Para desarrollo aislado, `docker compose --env-file .env.local up --build` desde este directorio usa `.env.local` para resolver `DATABASE_URL`, `INTERNAL_TOKEN`, JWT y CORS. En el stack completo, el despliegue central puede seguir orquestando puertos e infraestructura, pero los valores operacionales deben poder copiarse desde esta plantilla sin depender de otro microservicio.

Pydantic carga variables de entorno y `.env`; nombres no distinguen mayúsculas normalmente. `.env.example` es plantilla, no fuente de secretos.

| Variable | Default de código | Uso |
| --- | --- | --- |
| `APP_NAME` | `Flowkron Operational Service` | Título OpenAPI |
| `ENVIRONMENT` | `local` | Etiqueta de ambiente; no activa controles por sí sola |
| `DEBUG` | `True` | Setting disponible; FastAPI no lo usa actualmente al construir la app |
| `DATABASE_URL` | credencial local insegura | Engine SQLAlchemy PostgreSQL |
| `DATABASE_SCHEMA` | `operational` | Schema publico usado por las tablas de runtime/migracion/eventos |
| `DATABASE_GRANT_ROLE` | vacio | Rol opcional al que se otorgan permisos sobre schemas tenant; si queda vacio no ejecuta GRANT |
| `CORS_ALLOWED_ORIGINS` | localhost 4200/8080 | Lista CSV o JSON |
| `INTERNAL_TOKEN` | `change-me-local-internal-token` | Token compartido `/internal/*` |
| `JWT_PUBLIC_KEY` | vacío | PEM inline; tiene precedencia |
| `JWT_PUBLIC_KEY_PATH` | vacío | Ruta PEM alternativa |
| `JWT_ALGORITHM` | `RS256` | Algoritmo aceptado |
| `JWT_AUDIENCE` | `flowkron` | Audience requerida |
| `JWT_ISSUER` | `flowkron-auth-service` | Issuer requerido |
| `DEFAULT_PAGE_SIZE` | `50` | Disponible, pero routers fijan 50 explícitamente |
| `MAX_PAGE_SIZE` | `200` | Tope de listados |
| `TENANT_MIGRATION_VERSION` | `tenant_schema_v2` | Versión lógica en registry |
| `INGEST_RATE_LIMIT_PER_MINUTE` | `120` | Límite en memoria por tenant/proceso |
| `OPERATIONAL_PORT` | `8001` en Compose | Solo interpolación del puerto host |

Producción debe definir como mínimo `DATABASE_URL`, `INTERNAL_TOKEN`, una fuente de clave JWT y CORS explícito. Los defaults locales de DB/token no son aceptables.

## Docker

La imagen usa Python 3.12 slim y Uvicorn con un proceso. Compose no levanta PostgreSQL: `DATABASE_URL` debe apuntar a una instancia accesible. El contenedor escucha `PORT` si existe y cae a `8001`; `OPERATIONAL_PORT` solo publica el puerto host de Compose. El healthcheck consulta `/healthz` y `restart: unless-stopped` reinicia el contenedor.

El servicio comparte conceptualmente DB con auth, pero debe usar permisos mínimos: crear/alterar schemas tenant y tablas públicas necesarias. Evita exponer PostgreSQL directamente.

## Startup

El lifespan ejecuta `create_public_tables()` antes de servir. Esto requiere DB disponible y permisos DDL. No aplica Alembic automáticamente ni migra columnas existentes.
