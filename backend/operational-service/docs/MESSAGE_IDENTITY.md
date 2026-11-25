# FK-01: identidad persistida del mensaje

Decisión adoptada en código el 18 de noviembre de 2026; validada en PostgreSQL descartable. Aplicación a instalaciones existentes pendiente de su despliegue controlado.

## Fuente de verdad y recorrido

El conector normaliza la entrada y conserva el ID real de WhatsApp. Operational recibe `WhatsAppMessageIn`, escribe `operations.Message` en `mensajes_dashboard` y actualiza el resumen mediante el trigger existente. El CRM lee esa misma tabla mediante `conversation_service` y `message_to_dict`.

Se amplía la tabla activa. No se activa `tenant_models/message.py` ni se crea una tabla paralela `messages`. Ese módulo permanece como referencia histórica inactiva; no debe importarse al metadata productivo.

## Campos y significado

| Campo | Persistencia y compatibilidad |
| --- | --- |
| `id`, `whatsapp_id`, `rol`, `mensaje`, `creado_en` | Se conservan filas, claves y significado. La asociación de hilo sigue siendo `Conversation.session_id == Message.whatsapp_id` |
| `connection_id` | `default`, una sola conexión por empresa. La API rechaza otros valores hasta FK-14 |
| `channel` | `whatsapp` en el flujo actual |
| `external_message_id` | Identidad idempotente de ingestión; nullable para historial sin asociación demostrable |
| `provider_message_id` | ID del proveedor de ese mensaje específico; nullable. La respuesta usa su propio ID, nunca el ID entrante |
| `direction` | `inbound`/`outbound`, inferido de `rol` para historial y escritores antiguos |
| `message_type` | `text`; la API no habilita multimedia |
| `delivery_status` | Estado reportado por el adaptador: entrada omitida deriva `received`, salida omitida deriva `unknown`. El conector reporta `sent` tras `sendMessage`; eso no acredita entrega/lectura. Historial usa `unknown` |
| `recorded_at` | Momento de persistencia para mensajes nuevos; historial conserva `creado_en` porque no existe otra evidencia |

La lectura mantiene `sent_at` y `created_at` con su semántica anterior basada en `creado_en`. No se altera silenciosamente el significado de esos campos. `raw_payload` de lectura sigue siendo `{}`; esta tarea no agrega almacenamiento de payloads completos por mensaje.

`external_message_id` de lectura ahora devuelve el ID que efectivamente recibió ingestión. Para historial sin ese dato conserva el fallback anterior `str(id)`, que no debe usarse como ID del proveedor. El CRM consume `id` interno; no necesita migración de cliente. Otros consumidores que asumieran igualdad entre esos dos campos deben usar `id` para identidad interna.

## Deduplicación y concurrencia

La unicidad en base de datos es `(connection_id, channel, external_message_id)` dentro del schema de la empresa autenticada. Los valores null históricos no colisionan. Hay índice de consulta por `(connection_id, channel, provider_message_id)`.

La ingestión toma locks transaccionales PostgreSQL antes de consultar o crear datos: identidad externa, teléfono e hilo, con nombres que incluyen el schema autenticado. Permite reintentos concurrentes sin duplicar contacto, lead, conversación ni resumen. No cambia el mecanismo `schema_translate_map` ni la resolución del tenant.

Una repetición nueva devuelve `duplicate: true` y el `message_id` original sin cambiar nombres o payloads de conversación. Reutilizar esa identidad para otro hilo o dirección devuelve 409. Un marcador histórico en `mensajes_procesados` conserva `duplicate: true` con `message_id: null` si no hay correspondencia fiable. Se sigue escribiendo el marcador para permitir volver al código anterior sin perder esa deduplicación.

Esto no resuelve el turno incompleto tras guardar una entrada: esa recuperación es FK-02. Tampoco agrega recibos de entrega/lectura ni varias conexiones. Escritores de versiones antiguas no participan en los locks nuevos; no mezclar tráfico de ingestión de ambas versiones durante el cambio.

## Migración y operación

`apply_tenant_schema` serializa upgrades del mismo schema y ejecuta `upgrade_message_schema` dentro de su transacción. Se agregan columnas, se completa dirección/fecha histórica y se crean constraints/índices. Un trigger previo a inserción completa dirección para SQL/escritores anteriores que solo envían `rol`. Se mantienen los triggers de resumen. Repetir la migración no duplica filas ni reinicia sus contadores.

Para una instalación existente, en una ventana controlada:

1. Confirmar backup/restauración y ensayar con una copia. Esta migración toma locks de tabla y construye índices; medir duración con el volumen real.
2. Pausar ingestión y escrituras; iniciar el código nuevo sin exponer lecturas/escrituras de mensajes hasta completar el upgrade.
3. Establecer `TENANT_MIGRATION_VERSION=tenant_schema_v3` si la instalación fija ese valor; el default de código y `.env.example` ya están actualizados. No basta con cambiar la etiqueta.
4. Ejecutar la herramienta existente `scripts/migrate_all_tenants.py` o el endpoint interno de migraciones contra la base expresamente autorizada. Revisar cada resultado y `migration_registry`: el recorrido masivo incluye únicamente runtimes activos.
5. Antes de reactivar runtimes suspendidos, migrar también sus schemas usando el procedimiento de mantenimiento con `migrate_runtime`; no reactivarlos únicamente para migrarlos. No hay endpoint nuevo para esta tarea.
6. Si falla un schema, mantenerlo sin tráfico y corregir/reintentar. No servir el nuevo modelo sobre tablas sin upgrade. Validar lectura histórica, ingestión, ID de proveedor y deduplicación antes de reabrir tráfico.

Rollback: una migración fallida se revierte transaccionalmente. Para volver al código anterior después de un upgrade exitoso, pausar tráfico, restaurar la versión anterior y conservar columnas, índices y triggers aditivos. No ejecutar un downgrade que borre IDs nuevos; la versión anterior los ignora y sigue usando marcadores. Revalidar con backup/copia antes de aplicar en una instalación real.

## Evidencia de validación

La suite [test_message_identity.py](../tests/test_message_identity.py) crea su propio cluster PostgreSQL temporal, ligado solo a loopback, y lo detiene y elimina al terminar. No consume `DATABASE_URL` ni abre una base existente.

Verifica empresas nuevas, upgrade repetido sobre tabla histórica, rollback transaccional, compatibilidad con inserciones antiguas, concurrencia de duplicados y mensajes distintos, unicidad en base de datos, aislamiento entre schemas y lectura de metadatos. El conector comprueba que conserva IDs diferentes en entrada y salida.

No se aplicó esta migración a datos de la instalación del usuario. No se probó un canal real ni se desplegó el cambio.
