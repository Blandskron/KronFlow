# Modelo de datos

## Schema publico

Startup crea estas tablas con `Base.metadata.create_all`:

| Tabla | Proposito | Campos clave |
| --- | --- | --- |
| `tenant_runtime` | Mapea tenant IAM a schema/credencial ingest | `auth_tenant_id`, `tenant_slug`, `schema_name`, `tenant_code`, `ingest_key_hash`, `plan`, `status` |
| `migration_registry` | Estado por schema y version logica | `schema_name`, `migration_version`, `status`, `executed_at`, `error_message` |
| `system_events` | Eventos operacionales | `auth_tenant_id`, `schema_name`, `event_type`, `payload`, `created_at` |
| `billing_reference` | Referencia de billing no usada por routers actuales | `auth_tenant_id`, `provider`, `external_id`, `plan`, `status`, `payload` |

## Schema tenant activo

La fuente canonica está en `app/tenant_models/operations.py`, `app/tenant_models/context.py` y `app/tenant_models/whatsapp_turn.py`. El provisioning crea exclusivamente tablas incluidas en `ACTIVE_TENANT_TABLE_NAMES`.

| Tabla | Proposito |
| --- | --- |
| `mensajes_procesados` | Idempotencia por message ID externo |
| `clientes` | Persona/empresa, contacto, origen y consentimiento |
| `ejecutivos` | Ejecutivos y carga de asignacion |
| `leads` | Clasificacion, score, estado, seguimiento y ejecutivo |
| `inventario_vehiculos` | Inventario de concesionaria |
| `solicitudes_derechos` | Solicitudes de privacidad y plazos |
| `log_limpiezas` | Auditoria de limpieza/anonimizacion |
| `conversaciones` | `session_id`, ultimo payload JSON y fecha |
| `mensajes_dashboard` | Mensajes activos con identidad externa/proveedor, conexión, canal, dirección, tipo, estado reportado y fecha de registro; conserva WhatsApp ID, rol, texto y fecha originales |
| `whatsapp_turns` | FK-02: etapa por mensaje entrante, lease/token privado, respuesta preparada, handoff y referencia a salida; no duplica el historial |
| `reglas_negocio` | Reglas comerciales temporales por alcance JSON |
| `rate_limit` | Contador por WhatsApp ID y ventana temporal |
| `conversaciones_resumen` | Resumen materializado por WhatsApp ID |
| `tenant_agent_profiles` | Perfil/tono/resumen del agente por tenant |
| `business_context_documents` | Documentos validados de contexto empresarial |
| `document_chunks` | Fragmentos recuperables por RAG |
| `document_embeddings` | Estructura futura para vectores por chunk |
| `business_context_forms` | Blueprint de formularios base |
| `business_context_fields` | Campos del blueprint de formularios |
| `business_context_form_submissions` | Respuestas estructuradas si se reactiva el flujo de formularios |

## Relaciones y objetos

- `leads.cliente_id -> clientes.id` con cascade.
- `leads.ejecutivo_id -> ejecutivos.id`.
- Conversaciones/mensajes se relacionan logicamente mediante `session_id == whatsapp_id`; no hay FK.
- Los mensajes nuevos guardan el ID externo en `mensajes_dashboard`, con unicidad por conexión/canal dentro del schema autenticado. `mensajes_procesados` se mantiene por compatibilidad y deduplicación histórica; no es una segunda fuente de contenido. Sus marcadores antiguos no se asocian por suposición a filas del historial.
- `document_chunks.document_id -> business_context_documents.id` con cascade.
- `document_embeddings.chunk_id -> document_chunks.id` con cascade.
- Vista `v_inventario_disponible` filtra vehiculos disponibles.
- Triggers actualizan `actualizado_en` y resumen de conversaciones.

## Contexto del agente

Agent Core envia documentos ya extraidos y chunked a endpoints internos. Operational valida runtime, aplica `schema_translate_map` y persiste en el schema tenant correcto. Las queries de contexto tambien filtran por `tenant_id` logico como defensa adicional.

`business_context_documents` y `document_chunks` son la fuente de verdad del modulo Contexto Empresarial. `reglas_negocio` no almacena PDFs ni chunks RAG; sigue siendo para reglas comerciales estructuradas.

`business_context_documents` tiene constraint unica por `tenant_id + filename + version`. El servicio no confia en que Agent Core envie version: calcula la siguiente version disponible por archivo dentro del tenant y evita colisiones al re-subir un documento con el mismo nombre.

## Modulos legacy no activos

Los siguientes archivos declaran un modelo alternativo en ingles, pero no son importados por el flujo normal:

```text
agent_profile.py
analytics_snapshot.py
conversation.py
handoff_request.py
lead.py
lead_event.py
message.py
```

No existen hoy tablas activas `agent_profiles`, `analytics_snapshots`, `handoff_requests` o `lead_events`. El perfil activo del agente para el flujo nuevo es `tenant_agent_profiles`, definido en `tenant_models/context.py`.

## Migracion

`create_all` agrega tablas faltantes pero no altera columnas/constraints existentes. El provisioning ejecuta además `upgrade_message_schema` para FK-01, una migración transaccional e idempotente de la tabla activa, tanto en empresas nuevas como existentes. `tenant_schema_v3` etiqueta este estado. No elimina columnas ni reconstruye IDs históricos.

La [decisión de identidad de mensajes](MESSAGE_IDENTITY.md) documenta claves, compatibilidad, límites y despliegue. El modelo alternativo `message.py` permanece inactivo y explícitamente documentado como histórico.

`tenant_schema_v4` mantiene ese upgrade y agrega `whatsapp_turns` desde `tenant_models/whatsapp_turn.py`, importado por el metadata activo. No crea filas a partir de mensajes antiguos. Ver [recuperación de turnos](TURN_RECOVERY.md) para estados, atomicidad y reconciliación.

`tenant_schema_v5` agrega `whatsapp_turn_jobs` con un registro por turno admitido de forma durable. Conserva clave de cuenta, destinatario original, intentos y próxima disponibilidad. La eliminación de su turno elimina el trabajo correspondiente.

`tenant_schema_v6` agrega el índice `idx_messages_thread_id` para consultar mensajes por sesión e ID. El trigger conserva `conversaciones_resumen.no_leidos` al guardar respuestas de salida. Los mensajes entrantes incrementan el contador y el equipo lo reduce al marcar el último mensaje cargado. Los contadores previos se conservan tal como estaban al migrar.

`tenant_schema_v7` agrega `whatsapp_send_evidence`. Cada fila depende de un trabajo durable y reserva un ID del proveedor único por cuenta. Guarda el estado más fuerte observado y, cuando corresponde, un motivo de fallo normalizado. La reserva precede el envío. El estado final del mensaje se conserva en `mensajes_dashboard.delivery_status`.

`tenant_schema_v8` agrega `whatsapp_consent_state` por contacto. `decision_at` ordena comandos y `authorized_from` delimita el período de admisión de consultas cuando se conoce la hora de concesión. La migración conserva el consentimiento vigente y recupera la fecha de auditoría más reciente cuando existe.
