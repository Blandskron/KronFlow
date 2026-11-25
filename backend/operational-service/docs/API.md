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

`meta.tenant_id` usa primero el ID IAM del runtime resuelto (`TenantContext.auth_tenant_id`), tanto en éxitos como en errores. Si todavía no se resolvió runtime, puede usar el principal autenticado; sin identidad validada es `null`. Las cabeceras que declaran empresa no se copian a metadatos antes de autenticar. Esto corrige trazabilidad y no cambia la autorización de recursos.

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

Las rutas usan credenciales de ingestión por empresa: `X-Tenant-Code` + `X-Ingest-Key`, o el puente interno `X-Flowkron-Tenant` + `X-Baileys-Token`. Exigen runtime activo y admisión/tasa en memoria. El puente privado no se expone al navegador.

FK-02 añade siete operaciones bajo `/api/v1/ingest/whatsapp/turns`: `claim`, consulta por ID, `prepare`, `begin-send`, `complete`, `release` y `reconcile`. El [contrato y runbook de recuperación](TURN_RECOVERY.md) explica su orden, tokens, estados y límites. El endpoint anterior `/message` conserva su comportamiento para adaptadores existentes.

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

Todas las rutas siguientes exigen `Authorization: Bearer <JWT humano>`. Se validan firma RS256, issuer, audience, expiración, tipo de token, tenant y runtime activo. Las lecturas CRM requieren `users.read`, las escrituras de CRM requieren `crm.manage` y las rutas de agentes y auditoría comprueban sus permisos específicos.

### Leads

| Método y ruta | Detalle |
| --- | --- |
| `GET /api/v1/leads` | Paginación por fecha de actualización e ID descendentes; filtros `q`, `contact_id`, `status_group`, `temperature`, `lifecycle_status`, `direction` |
| `GET /api/v1/leads/{lead_id}` | Detalle y `contact_id` de la empresa. Requiere `users.read`. |
| `PATCH /api/v1/leads/{lead_id}` | Actualiza nombre/email/clasificación/estado/ejecutivo/score. `expected_updated_at` protege la edición contra cambios posteriores (`409`). |
| `GET /api/v1/leads/{lead_id}/activity` | Requiere `audit.read`. Devuelve el alta manual y los cambios comerciales de etapa o temperatura. `limit` admite entre 1 y 50 filas. |

`direction` en el filtro: cualquier valor distinto de `inbound` fuerza una consulta vacía. En `LeadUpdate`, los campos `direction`, `tags` y `metadata` están aceptados por Pydantic pero el service no los persiste actualmente.

`q` busca una subcadena literal por nombre, correo o teléfono. `status_group=closed` incluye `ganado` y `perdido`, y `open` incluye las demás etapas. `contact_id` filtra por la referencia tenant del lead. Los cambios de etapa y temperatura desde CRM quedan auditados en la misma transacción, con el ID y los valores previos y nuevos. El historial expone solo estos eventos y el alta manual, ordenados del más reciente al más antiguo. Una etapa, clasificación, puntuación o asignación inválida devuelve `422`.

### Conversaciones y mensajes

`GET /api/v1/conversations/handoff-history` requiere `users.read`. Devuelve derivaciones persistidas a partir de `whatsapp.turn.handoff` e `ingest.handoff.created`, en orden descendente por ID. `limit` admite de 1 a 50 y `before_id` continúa desde `next_before_id`. La cola vigente se consulta con `GET /api/v1/conversations?requires_human=true`.

Las derivaciones de WhatsApp resuelven la conversación visible en la Bandeja y su lead. Las derivaciones de entrada anteriores resuelven el lead registrado por el evento. Si el destino ya no existe, el historial conserva el evento con sus referencias nulas. La API entrega la fecha, el tipo, el nombre si hay un destino y los IDs para navegar. Los textos de mensajes y los payloads de auditoría quedan en sus fuentes.

| Método y ruta | Detalle |
| --- | --- |
| `GET /api/v1/conversations` | Filtros SQL `status`, `channel`, `requires_human`, `q` y `contact_id`. Admite continuación por `before_at` y `before_id`; conserva `offset` |
| `GET /api/v1/conversations/{id}` | Detalle |
| `POST /api/v1/conversations/{id}/read` | Lectura compartida hasta `through_message_id`, con permiso `crm.manage`. Devuelve el contador `no_leidos` |
| `GET /api/v1/conversations/{id}/messages` | Mensajes asociados por `session_id/whatsapp_id` |

La búsqueda compara una subcadena literal del nombre, teléfono, sesión o texto del último mensaje en el resumen. El endpoint ordena por fecha del resumen e ID en orden descendente. Para avanzar, enviar los dos campos de `next_cursor` con los mismos filtros. Actualizar la primera página para incorporar conversaciones que hayan subido en el orden. La paginación de mensajes conserva su propio cursor.

El contador es compartido por el equipo. Un usuario con `crm.manage` puede marcar los mensajes hasta un ID cargado de esa conversación. Los mensajes entrantes más recientes siguen pendientes. El contador acredita actividad en el CRM y los recibos del proveedor se rigen por el estado de cada mensaje.

Los mensajes de salida exponen `delivery_status` y el motivo normalizado cuando existe. La primera página con `order=recent` incluye `pending_replies`, estados de procesamiento de respuestas enlazados al mensaje entrante. Los recibos del conector se reciben por la ruta privada descrita en el [procedimiento de turnos](TURN_RECOVERY.md#recibos-del-proveedor).

El modelo activo de conversación es un JSON por `session_id`, no la tabla relacional descrita por los módulos legacy.

`contact_id` incluye hilos cuyo lead asociado en la Bandeja referencia ese contacto. Los hilos sin un lead asociado quedan fuera de ese filtro.

### Contactos

`GET /api/v1/contacts` consulta el directorio de la empresa autenticada con `users.read`. Admite `limit`, `offset`, `source` para filtrar por origen exacto y `q` para buscar por nombre, correo, teléfono e identificador WhatsApp sin distinguir mayúsculas. Las consultas con formato telefónico y al menos cuatro dígitos comparan también los números sin puntuación. El orden es fecha de creación e ID descendentes. `data` incluye `items`, `total`, `limit` y `offset`.

`GET /api/v1/contacts/sources` devuelve hasta cien orígenes únicos ordenados de la empresa activa. `GET /api/v1/contacts/{contact_id}` conserva los campos del listado y añade `normalized_email` y `normalized_phone`. Devuelve `404` cuando el contacto no existe en la empresa. Ambos requieren `users.read`.

`GET /api/v1/contacts/{contact_id}/whatsapp-consent` requiere `audit.read` y devuelve el estado de WhatsApp, la última decisión conocida y el historial de la empresa del JWT. Admite `limit` de 1 a 50 (15 por defecto) y `before_id` con el cursor `next_before_id` de la respuesta. Ordena el historial por ID de registro descendente y calcula el estado vigente independientemente de la página. Una baja recibida tarde que corresponde a un periodo anterior aparece como `prior_withdrawal`. Se incluyen fechas y versiones de política reconocibles. La consulta utiliza el consentimiento guardado cuando la proyección de orden v8 todavía no está disponible.

La ficha calcula los valores al leer. Para un buzón ASCII compatible, conserva mayúsculas, puntos y alias de la parte local y pasa el dominio a minúsculas. Para un teléfono con `+` explícito, quita los separadores del formato internacional admitido. Devuelve `null` ante un valor ausente o un formato ambiguo. Los resultados representan formato, sin evidencia de titularidad, disponibilidad ni consentimiento. [Regla de mayúsculas de SMTP](https://www.rfc-editor.org/rfc/rfc5321.html#section-2.4) · [Formato internacional E.164](https://www.itu.int/rec/T-REC-E.164/en)

`POST /api/v1/contacts` requiere `crm.manage`. Recibe `request_id` en UUID v4, `full_name` y, opcionalmente, `email` y `phone`. Persiste el contacto con origen `crm_manual`, `whatsapp_id` vacío y consentimiento desactivado. Devuelve `contact` y `created`. El UUID identifica un alta dentro de la empresa. Al repetir ese UUID, incluso después de editar la ficha, se devuelve el registro vigente con `created: false` y se ignoran los nuevos valores de la solicitud. Para otra alta se usa un UUID distinto. Esta protección cubre el reintento de la solicitud. La detección de contactos equivalentes sigue siendo parte de la identidad multicanal de FK-28.

`PATCH /api/v1/contacts/{contact_id}/points` requiere `crm.manage` y un contacto de origen `crm_manual`. Recibe el correo y teléfono (`null` para borrar) y los valores anteriores `expected_email` y `expected_phone`. El servidor compara ambos datos bajo bloqueo y devuelve `409` si cambiaron. En un cambio efectivo se auditan el ID y los campos modificados. Los contactos de integración conservan su flujo de actualización de origen.

`PATCH /api/v1/contacts/{contact_id}` requiere `crm.manage` y guarda `full_name` si `expected_full_name` coincide con el registro bajo bloqueo. Devuelve `409` si el contacto cambió y registra una auditoría con el ID al guardar un nombre distinto. La operación conserva los datos de contacto y las decisiones de consentimiento existentes.

`POST /api/v1/contacts/{contact_id}/lead` requiere `crm.manage`. Devuelve `lead` y `created`. Si el contacto ya tiene un lead, devuelve el primero por ID, incluso si está cerrado. Si carece de lead, crea uno con etapa `nuevo` y temperatura `cold`, y registra el alta en la misma transacción. Las altas simultáneas reutilizan el mismo lead. La operación usa el contacto existente y deja la atención y el consentimiento en sus flujos actuales.

### Analytics

`GET /api/v1/analytics/summary` devuelve conteos de leads por clasificación, hilos abiertos del inbox, hilos en espera de atención y mensajes. Las ventanas de mensajes son desde medianoche UTC y los últimos siete días hasta el instante de evaluación. El resumen usa los mismos hilos y estados que la Bandeja y calcula todos los conteos sobre una misma instantánea de PostgreSQL.

`GET /api/v1/analytics/activity` requiere `users.read` y consulta la empresa del JWT. Recibe `start_date` y `end_date` como fechas inclusivas, hasta 31 días, y `time_zone` con una zona IANA de región o `UTC`. Ambas fechas se interpretan en esa zona. Devuelve `422` si la zona, el orden o la extensión son inválidos, o si el fin excede el día de hoy en la zona elegida.

La respuesta incluye `as_of` en UTC, `partial_day` cuando el último día sigue en curso, una fila por día y totales que suman las filas. Contactos y leads se cuentan por `creado_en`. Los mensajes se cuentan por `creado_en` y dirección persistida. Los salientes registrados pueden estar en cualquier estado de entrega. Los días sin actividad tienen cero. Todas las métricas de actividad salen de una consulta tenantizada sobre las tablas operacionales.

### Eventos de auditoría

`GET /api/v1/operational/audit-events` requiere `audit.read`. Filtra por la empresa autenticada, `event_type` opcional y un `correlation_id` UUID opcional. `limit` admite de 1 a 50. Para continuar hacia atrás por ID, envía `next_before_id` como `before_id` con los mismos filtros.

El endpoint proyecta altas y cambios de contactos y leads, derivaciones y transiciones de privacidad. Devuelve ID estable del evento en esta instalación, un tipo de catálogo, versión `v1`, hora de registro y empresa. `data` contiene referencias internas y, cuando corresponde, etapas o estados de un catálogo cerrado. Para auditorías con una correlación UUID válida se conserva ese identificador. En registros históricos o sin UUID se usa el ID del propio evento como referencia, sin atribuirlo a una solicitud. Esta paginación consulta historia registrada. Los cursores de consumo, las garantías de replay hacia delante y las suscripciones siguen pendientes.

### Seguimiento de privacidad

`GET /api/v1/operational/privacy-cases` requiere `audit.read`. Pagina por fecha límite e ID y acepta `state`. Devuelve ID, tipo, estado y fechas de seguimiento. `PATCH /api/v1/operational/privacy-cases/{case_id}` requiere también `crm.manage`. Admite `pendiente → en_proceso` y `en_proceso → completada`. El cierre exige `confirmed: true`, registra la fecha y audita el actor junto con la transición. Un reintento de la transición ya aplicada conserva la fecha y el evento originales. El cierre registra una gestión confirmada. La ejecución de la solicitud y el tratamiento de copias quedan en su proceso específico.

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
