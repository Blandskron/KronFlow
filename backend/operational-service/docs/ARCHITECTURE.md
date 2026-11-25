# Arquitectura

## Responsabilidad

Servicio operacional multi-tenant de Flowkron. Conserva metadatos de runtime en el schema publico y datos de negocio en un schema PostgreSQL por tenant. La identidad, memberships, RBAC y suscripciones son responsabilidad de `flowkron-auth-service`.

Operational tambien es el duenio del DDL tenant usado por Agent Core para contexto empresarial. Agent Core no calcula `schema_name` ni accede directamente a PostgreSQL en el stack integrado.

## Flujo de request

```text
Dashboard -- JWT humano --> get_current_principal --> TenantRuntime --> schema_translate_map
Ingest/el adaptador -- code+key --> verify PBKDF2 hash --> TenantRuntime --> schema_translate_map
Auth service -- internal token --> provisioning/status/migrations --> public + tenant schemas
Agent Core -- internal token + tenant_id --> TenantRuntime --> schema_translate_map --> context/RAG tables
```

`resolve_tenant_from_jwt` valida RS256, issuer, audience y expiracion; extrae `tenant_id`, busca runtime y exige `status=active` y plan no Free. La ingestion realiza la misma comprobacion de runtime despues de validar sus headers. Los endpoints internos de contexto resuelven runtime por `auth_tenant_id`.

## Aislamiento

Los modelos activos declaran `schema="tenant"`. Cada ejecucion usa `schema_translate_map={"tenant": runtime.schema_name}` mediante `tenant_exec_options`, `execute_for_tenant`, `scalar_for_tenant` o `bind_tenant_session`.

El servicio no ejecuta `SET search_path` por request. `sanitize_schema_name` normaliza el slug durante provisioning; los requests posteriores usan el `schema_name` persistido en `TenantRuntime`.

Ningun cliente externo debe enviar `schema_name`. Frontend, el adaptador y Agent Core trabajan con JWT, tenant code o tenant ID logico; Operational traduce a schema fisico.

## Provisioning

1. Valida `X-Internal-Token` y payload.
2. Si ya existe runtime, devuelve el existente sin nueva ingest key; si estaba `provision_failed`, intenta reaplicar el schema.
3. Para uno nuevo, genera schema unico, tenant code e ingest key; almacena solo su hash PBKDF2.
4. Crea tablas activas, vista `v_inventario_disponible`, funciones/triggers y objetos auxiliares.
5. Registra migration y `system_events`; entrega ingest key una sola vez.

La creacion usa SQLAlchemy `create_all`, no revisiones Alembic tenant. `migrate_all_tenants()` reaplica el proceso a todos los runtimes activos y es necesario cuando se agregan tablas tenant activas.

## Persistencia activa y legado

`app/tenant_models/__init__.py` importa modelos operacionales y modelos de contexto empresarial. `tenant_provisioning_service.py` crea solo las tablas declaradas en `ACTIVE_TENANT_TABLE_NAMES`.

Modelos activos:

- `operations.py`: datos de concesionaria, WhatsApp, leads, conversaciones dashboard, reglas comerciales, rate limit y resumen.
- `context.py`: contexto documental del agente, chunks RAG, embeddings futuros, perfil del agente y blueprint de formularios.

Modelos legacy no activos:

- `agent_profile.py`
- `analytics_snapshot.py`
- `conversation.py`
- `handoff_request.py`
- `lead.py`
- `lead_event.py`
- `message.py`

Algunos legacy duplican nombres de tabla con metadata incompatible; no deben importarse en el flujo normal.

## APIs de negocio

- `/api/v1/leads` y `/conversations` adaptan tablas activas al contrato frontend en ingles.
- `/api/v1/operational/*` expone columnas nativas para las colecciones operacionales soportadas.
- `/api/v1/ingest/whatsapp/*` es el contrato de adaptadores WhatsApp.
- `/api/v1/analytics/summary` calcula metricas en vivo.
- `/api/v1/agents` esta registrado pero no implementado funcionalmente.
- `/internal/tenants/{tenant_id}/context/*` es el contrato interno usado por Agent Core para documentos, status y retrieval RAG.

el adaptador no debe conectarse directo a schemas tenant para datos de negocio. Debe llamar a Operational con `X-Tenant-Code` y `X-Ingest-Key`; Operational resuelve el schema persistido y ejecuta con `schema_translate_map`. Agent Core tampoco recibe ni calcula `schema_name`; llama endpoints internos con `tenant_id` logico e `X-Internal-Token`.

## Migraciones

Alembic esta configurado para excluir metadata con schema `tenant` y atender tablas publicas, pero no hay revisiones versionadas. Startup llama `create_public_tables()` y crea tablas publicas faltantes sin migrar columnas existentes.

`migrate_all_tenants()` selecciona runtimes activos y vuelve a aplicar `create_all`, vistas, funciones y triggers; registra una version logica configurable. Este mecanismo es aditivo/idempotente, no sustituye migraciones explicitas para cambios destructivos o alteraciones de columnas.
