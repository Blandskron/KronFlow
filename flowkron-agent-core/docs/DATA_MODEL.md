# Data Model

Agent Core define entidades transversales de conversacion, contexto, chunks, reglas y trazas. Esas tablas describen el blueprint funcional del agente, pero en arquitectura integrada el ownership de schema pertenece a `flowkron-operational-service`.

Regla de ownership:

- Operational provisiona tenants, industrias, schemas y migraciones reales.
- Agent Core no crea schemas ni tablas en produccion.
- Agent Core puede crear tablas solo en modo local/test con `ALLOW_LOCAL_DB_BOOTSTRAP=true`.
- Toda entidad persistente transversal debe incluir `tenant_id`.

Esto permite que a futuro cada industria use schemas distintos sin que el core IA conozca detalles fisicos de escritura.

## Tablas productivas delegadas

Operational crea y mantiene en cada schema tenant las tablas de contexto que Agent Core consume por API interna:

| Tabla | Uso |
| --- | --- |
| `tenant_agent_profiles` | Perfil/tono/resumen del agente por tenant |
| `business_context_documents` | Documento validado cargado por la empresa |
| `document_chunks` | Fragmentos recuperables para RAG |
| `document_embeddings` | Estructura futura para vectores por chunk |
| `business_context_forms` | Blueprint de formularios base |
| `business_context_fields` | Campos del blueprint de formularios |
| `business_context_form_submissions` | Respuestas estructuradas si se reactiva el flujo de formularios |

En modo integrado, `POST /api/v1/context/documents/upload-file` no inserta en SQLite ni memoria local: extrae texto/chunks y llama a Operational. `/api/v1/agent/simulate` recupera fuentes desde Operational, por lo que una DB vacia debe producir cero documentos/fuentes.

El modelo `DocumentRead` expuesto por Agent Core incluye `version`. Si se carga nuevamente el mismo `filename` para el mismo tenant, la version productiva debe ser asignada por Operational para respetar la restriccion unica `(tenant_id, filename, version)` sin devolver 500 al usuario.

El status agregado de contexto usa `RECOMMENDED_CONTEXT_DOCUMENTS=5`: cero documentos produce `agent_status=not_configured`; documentos activos por debajo de cinco producen `pending`; cinco o mas activos producen `trained`; documentos en `rejected` o `error` producen `error`.

## Local/test

Los modelos SQLAlchemy en `app/models` siguen existiendo para validar el blueprint en SQLite/PG local. Esa ruta se activa explicitamente con:

- `PERSISTENCE_MODE=local`
- `ALLOW_LOCAL_DB_BOOTSTRAP=true`

No debe usarse para el stack integrado.
