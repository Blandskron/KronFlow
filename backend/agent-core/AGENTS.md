# AGENTS.md

Reglas para agentes de programación que trabajen en `backend/agent-core`.

## Antes de cambiar código

- Leer `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/SECURITY.md`, `docs/EVALUATION.md` y [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).
- Revisar si `backend/operational-service` o `backend/auth-service` ya resolvieron el patrón que se quiere modificar.
- No leer ni copiar secretos de `.env`, llaves privadas, tokens ni credenciales.

## Qué se puede modificar

- Código de aplicación bajo `app/`.
- Tests bajo `app/tests/`.
- Documentación bajo `docs/`.
- Skills locales bajo `skills/`.

## Qué requiere aprobación humana

- Cambios de contrato público.
- Cambios de autenticación, permisos, tenant isolation o migraciones destructivas.
- Integraciones reales con LLM, vector DB, email, agenda, tickets o CRM.
- Configuración de producción, dominios, CI/CD, secretos o infraestructura.

## Contratos

El endpoint universal `/api/v1/agent/messages` debe mantenerse canal-agnóstico. Cualquier gateway debe tratarse como adaptador externo.

## Estructura estándar

- `app/main.py`: FastAPI, middleware, routers y health checks.
- `app/core`: configuración, seguridad, contrato API, DB local/test y tenant context.
- `app/api/v1`: rutas públicas versionadas.
- `app/schemas`: DTOs públicos o aliases hacia `app/api/v1/schemas`.
- `app/services`: facade de casos de uso o aliases hacia `app/application`.
- `docs`: documentación operativa y de evaluación.

La capa `app/application`, `app/domain` y `app/infrastructure` es una extensión intencional para IA/RAG/adapters. No eliminarla solo para igualar carpetas.

## Modelo de datos

Toda entidad persistente transversal debe incluir `tenant_id` salvo catálogos globales justificados. No mezclar datos entre tenants en queries, tests o trazas. `agent-core` no mantiene migraciones Alembic propias; el DDL real debe ser provisionado por `operational-service`.

## Seguridad

No loguear payloads completos si contienen PII. En producción se debe usar JWT RS256 emitido por `auth-service`; `X-Tenant-Id` es solo para desarrollo local.
