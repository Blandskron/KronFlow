# AGENTS.md

Reglas para agentes de programacion que trabajen en `flowkron-agent-core`.

## Antes de cambiar codigo

- Leer `docs/agent/DISCOVERY.md`, `docs/agent/DATA_SCHEMA.md`, `docs/agent/SECURITY.md` y los contratos de `flowkron-api-contracts`.
- Revisar si operational o auth ya resolvieron el patron que se quiere modificar.
- No leer ni copiar secretos de `.env`, llaves privadas, tokens ni credenciales.
- Documentar supuestos nuevos en `docs/agent/DISCOVERY.md`.

## Que se puede modificar

- Codigo de aplicacion bajo `app/`.
- Tests bajo `app/tests/`.
- Documentacion bajo `docs/agent/`.
- Skills locales bajo `skills/`.

## Que requiere aprobacion humana

- Cambios de contrato publico.
- Cambios de autenticacion, permisos, tenant isolation o migraciones destructivas.
- Integraciones reales con LLM, vector DB, email, agenda, tickets o CRM.
- Configuracion de produccion, dominios, CI/CD, secretos o infraestructura.

## Contratos

El endpoint universal `/api/v1/agent/messages` debe mantenerse canal-agnostico. Cualquier gateway debe tratarse como adaptador externo.

## Estructura estandar

- `app/main.py`: FastAPI, middleware, routers y health checks.
- `app/core`: configuracion, seguridad, contrato API, DB local/test y tenant context.
- `app/api/v1`: rutas publicas versionadas.
- `app/schemas`: DTOs publicos o aliases hacia `app/api/v1/schemas`.
- `app/services`: facade de casos de uso o aliases hacia `app/application`.
- `docs`: documentacion raiz comparable con operational.

La capa `app/application`, `app/domain` y `app/infrastructure` es una extension intencional para IA/RAG/adapters. No eliminarla solo para igualar carpetas.

## Modelo de datos

Toda entidad persistente transversal debe incluir `tenant_id` salvo catalogos globales justificados. No mezclar datos entre tenants en queries, tests o trazas. `flowkron-agent-core` no mantiene migraciones Alembic propias; el DDL real debe ser provisionado por `flowkron-operational-service`.

## Seguridad

No loguear payloads completos si contienen PII. En produccion se debe usar JWT RS256 emitido por auth; `X-Tenant-Id` es solo para desarrollo local.
