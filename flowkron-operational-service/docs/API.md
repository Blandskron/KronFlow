# API y contratos

Base local: `http://localhost:8001`. Swagger: `/docs`; ReDoc: `/redoc`; schema: `/openapi.json`.

## Convenciones de contrato

Todas las respuestas JSON de runtime, incluyendo health, rutas internas, ingest y dashboard, se envuelven con el contrato compartido:

```json
{
  "success": true,
  "status": { "code": 200, "message": "Request completed successfully" },
  "data": {},
  "meta": {
    "api_version": "v1",
    "service": "operational-service",
    "tenant_id": null,
    "user_id": null,
    "request_id": "uuid",
    "correlation_id": "uuid",
    "trace_id": null,
    "timestamp": "2026-06-23T00:00:00Z"
  }
}
```

Los errores usan `ApiError` problem-details con `type`, `title`, `status`, `detail`, `instance`, `error_code`, `errors` y `meta`. El middleware conserva `X-Request-ID` y `X-Correlation-ID`. `/docs`, `/redoc` y `/openapi.json` no se envuelven.

## Health

| Método y ruta | Auth | Respuesta |
| --- | --- | --- |
| `GET /healthz` | No | `data.status="ok"`; solo proceso web |
| `GET /readyz` | No | Ejecuta `SELECT 1`; retorna `data.status="ready"` si funciona, pero una excepcion de DB puede terminar en `ApiError` 500 |

## Endpoints internos

Todos exigen `X-Internal-Token` con comparación constante.

| Método y ruta | Propósito |
| --- | --- |
| `POST /internal/tenants/provision` | Crea/reutiliza runtime y schema; 201 incluso si ya existía |
| `GET /internal/tenants/{tenant_id}/runtime` | Consulta runtime público |
| `POST /internal/tenants/{tenant_id}/suspend` | Cambia estado a suspended |
| `POST /internal/tenants/{tenant_id}/activate` | Cambia estado a active |
| `POST /internal/tenants/{tenant_id}/rotate-ingest-key` | Reemplaza hash y devuelve key nueva una vez |
| `POST /internal/migrations/run-all` | Reaplica objetos a runtimes activos y devuelve resultados |

Provision request:

```json
{
  "auth_tenant_id": 1,
  "tenant_slug": "demo-tenant",
  "tenant_name": "Demo opcional",
  "plan": "starter"
}
```

`tenant_name` se valida pero no se persiste. Si el runtime es nuevo, la respuesta contiene `ingest_key` y `created=true`; si ya existe, `ingest_key=null` y `created=false`.

### Contexto interno para Agent Core

Estos endpoints tambien exigen `X-Internal-Token` y son consumidos solo por `flowkron-agent-core`:

| Metodo y ruta | Proposito |
| --- | --- |
| `POST /internal/tenants/{tenant_id}/context/documents` | Crea documento de contexto y chunks en el schema tenant resuelto |
| `GET /internal/tenants/{tenant_id}/context/documents` | Lista documentos de contexto del tenant |
| `GET /internal/tenants/{tenant_id}/context/status` | Devuelve progreso, estado y documentos activos |
| `POST /internal/tenants/{tenant_id}/context/retrieve` | Recupera chunks/fuentes para RAG lexical |

El `tenant_id` de la ruta es el ID logico de Auth/IAM. Operational resuelve `tenant_runtime.schema_name` y aplica `schema_translate_map`; ningun consumidor debe enviar `schema_name`.

`POST /context/documents` recibe texto ya extraido y chunks desde Agent Core. El payload puede incluir `tenant_id`, pero debe coincidir con el tenant resuelto por la ruta o responde 403. Operational asigna `version` automaticamente como `max(version)+1` por `tenant_id + filename`; si se sube el mismo archivo mas de una vez, no falla por la constraint unica y crea una nueva version.

`GET /context/status` calcula progreso con cinco documentos activos recomendados, devuelve `agent_status` (`not_configured`, `processing`, `pending`, `trained` o `error`) y actualmente reporta `document_actions` en `false` para `delete`, `patch`, `replace` y `retry_processing`. `POST /context/retrieve` solo considera chunks de documentos `active`, usa busqueda lexical por tokens y limita `limit` entre 1 y 10.

## Ingesta WhatsApp

Todas las rutas exigen `X-Tenant-Code` y `X-Ingest-Key`, runtime activo, plan pagado y rate limit en memoria.

| Método y ruta | Acción |
| --- | --- |
| `POST /api/v1/ingest/whatsapp/message` | Upsert cliente/lead/conversación y crea mensaje idempotente por `external_message_id` |
| `POST /api/v1/ingest/whatsapp/lead-classification` | Actualiza clasificación, estado, score y resumen |
| `POST /api/v1/ingest/whatsapp/handoff` | Marca lead `en_proceso` / `requiere_humano` |
| `POST /api/v1/ingest/whatsapp/status` | Mezcla status dentro del JSON de conversación si existe |
| `GET /api/v1/ingest/whatsapp/inventory` | Lista inventario disponible para contexto IA |
| `GET /api/v1/ingest/whatsapp/customer?phone=...` | Devuelve cliente por WhatsApp si existe |
| `GET /api/v1/ingest/whatsapp/consent?phone=...` | Consulta consentimiento |
| `POST /api/v1/ingest/whatsapp/consent` | Registra consentimiento aceptado |
| `POST /api/v1/ingest/whatsapp/client` | Upsert de cliente desde lead el adaptador |
| `POST /api/v1/ingest/whatsapp/lead` | Upsert de lead enriquecido desde el adaptador |
| `POST /api/v1/ingest/whatsapp/privacy-requests` | Registra solicitud de derecho de datos |
| `POST /api/v1/ingest/whatsapp/dashboard-messages` | Registra mensaje usuario/agente para dashboard |
| `POST /api/v1/ingest/whatsapp/executives/assign` | Asigna ejecutivo activo round-robin y vincula lead |
| `POST /api/v1/ingest/whatsapp/executives/link` | Vincula lead a ejecutivo ya seleccionado |

Message requiere `external_message_id`, `phone`, `sent_at`; admite `external_thread_id`, nombre, email, dirección, body y raw payload. El canal permitido es únicamente `whatsapp`.

La idempotencia usa `mensajes_procesados.message_id`. En un duplicado se conserva/actualiza cliente y conversación antes de devolver `duplicate=true`, pero no se crea otro mensaje.

Los endpoints extendidos existen para que el adaptador no escriba directo en PostgreSQL ni en un schema fijo. el adaptador debe enviar solo `X-Tenant-Code` y `X-Ingest-Key`; Operational resuelve `TenantRuntime` y aplica `schema_translate_map`.

## Dashboard JWT

Todas las rutas siguientes exigen `Authorization: Bearer <JWT humano>`. Se valida firma RS256, issuer, audience, expiración y claim `tenant_id`; además runtime activo y plan distinto de Free.

Importante: hoy no se exigen permisos como `users.read`, `crm.manage` o `agents.create`; `require_permission` no está conectado a estos routers.

### Leads

| Método y ruta | Detalle |
| --- | --- |
| `GET /api/v1/leads` | Paginación; filtros `temperature`, `lifecycle_status`, `direction` |
| `GET /api/v1/leads/{lead_id}` | Detalle adaptado al contrato frontend |
| `PATCH /api/v1/leads/{lead_id}` | Actualiza nombre/email/clasificación/estado/ejecutivo/score |

`direction` en el filtro: cualquier valor distinto de `inbound` fuerza una consulta vacía. En `LeadUpdate`, los campos `direction`, `tags` y `metadata` están aceptados por Pydantic pero el service no los persiste actualmente.

### Conversaciones y mensajes

| Método y ruta | Detalle |
| --- | --- |
| `GET /api/v1/conversations` | Filtros `status`, `channel`, `requires_human`; paginación en memoria tras adaptar registros |
| `GET /api/v1/conversations/{id}` | Detalle |
| `GET /api/v1/conversations/{id}/messages` | Mensajes asociados por `session_id/whatsapp_id` |

El modelo activo de conversación es un JSON por `session_id`, no la tabla relacional descrita por los módulos legacy.

### Analytics

`GET /api/v1/analytics/summary` devuelve conteos de leads por clasificación, abiertos, handoff y mensajes de hoy/últimos siete días. Se calculan en vivo.

### Agents (stub)

| Método y ruta | Comportamiento actual |
| --- | --- |
| `GET /api/v1/agents` | `[]` |
| `POST /api/v1/agents/configure` | 501 Not Implemented |
| `PATCH /api/v1/agents/{id}` | 404 |

### Colecciones operacionales

Todos devuelven `data={items,total,limit,offset}` con columnas nativas:

- `GET /api/v1/operational/clientes`
- `GET /api/v1/operational/leads`
- `GET /api/v1/operational/inventario-vehiculos?disponible=true|false`
- `GET /api/v1/operational/conversaciones`
- `GET /api/v1/operational/mensajes-dashboard?whatsapp_id=...`
- `GET /api/v1/operational/solicitudes-derechos`
- `GET /api/v1/operational/ejecutivos`
- `GET /api/v1/operational/log-limpiezas`

## Paginación y errores

`limit` debe ser ≥1 y se trunca a `MAX_PAGE_SIZE`; `offset` ≥0. FastAPI usa 401 para credencial ausente/inválida, 402 para plan Free, 403 para runtime no activo/token sin tenant, 404 para runtime/recurso inexistente, 422 para payload inválido, 429 para ingest rate limit, 501 para configuración de agente y 503 cuando no hay clave JWT configurada. En runtime esos casos se devuelven como `ApiError` con `error_code` normalizado `OPERATIONAL_<status>_<reason>` o `PLATFORM_<status>_<reason>`.
