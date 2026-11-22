# Campañas, plantillas y entrega outbound

**Estado:** especificación propuesta. Depende del [ADR de módulos](02-architecture-adrs.md) y de [contactos y consentimiento](03-inbound-crm.md). El [gateway actual](../../../smtp-http-blandskron/app/main.py) envía correo y devuelve aceptación del proveedor. Su [webhook](../../../smtp-http-blandskron/app/webhooks.py) verifica firma y deduplica en memoria. El [conector Baileys](../../../flowkron-baileys-services/README.md) y los [turnos de Operational](../../../flowkron-operational-service/docs/TURN_RECOVERY.md) evidencian patrones de transporte, recibos y recuperación.

## Alcance v1 y proveedores

| Canal | Alcance propuesto y condición de habilitación |
| --- | --- |
| Email | MUST para una v1 con outbound real. Primero ejecutar el recorrido con proveedor stub. Habilitar Resend por empresa solo con remitente verificado y autorizado, bajas funcionales, cuotas y recibos persistidos. Confirmar comportamiento en un sandbox autorizado antes del release. |
| WhatsApp | Demo sintética del diseño. Habilitación real por empresa condicionada a un adaptador autorizado de WhatsApp Business Platform, cuenta vinculada, plantillas aprobadas cuando corresponda e integración de consentimiento y recibos. Si faltan esos gates, la interfaz mantiene el canal de campañas deshabilitado y la documentación limita el release a email. [Política de mensajes de WhatsApp Business](https://business.whatsapp.com/policy/preview?lang=es_LA) |
| Baileys | Se conserva el recorrido existente de laboratorio y atención inbound. La interfaz y el worker no ofrecen Baileys como proveedor de campañas. |

Operar cada canal requiere configuración del operador. El modo demo selecciona el stub mediante configuración de servidor y permite exclusivamente destinatarios sintéticos. La interfaz muestra canal, proveedor y entorno antes de confirmar cualquier salida. Las ventanas y exigencias del proveedor se comprueban nuevamente al ejecutar, incluida la revisión y vigencia de plantillas de WhatsApp. [Política de WhatsApp Business](https://business.whatsapp.com/policy/preview?lang=es_LA)

## Plantillas, segmentación y aprobación

1. Editor con plantillas versionadas e idioma. Email admite asunto, texto y HTML sanitizado. WhatsApp referencia la plantilla, idioma y categoría aprobados del proveedor. Las variables se declaran con tipo, límite y contexto. Escapar cada valor para su contexto, validar URLs de protocolos permitidos y rechazar plantillas incompletas o con contenido activo. Vista previa aislada sin scripts ni carga automática de recursos remotos.
2. Segmentar mediante filtros tipados por etiquetas, grupo, origen o etapa y un único canal por campaña. Ofrecer previsualización de recuento por elegibilidad, exclusión y contacto en conflicto. Cuando se aprueba la campaña se persiste un snapshot deduplicado de puntos de contacto elegibles. La evaluación de la elegibilidad se repite antes de enviar. Los contactos nuevos que entren al segmento tras la aprobación quedan para una campaña posterior.
3. El revisor aprueba versión exacta de plantilla, remitente, snapshot, finalidad, zona IANA, límites y ventana local. Una edición relevante invalida la aprobación. El actor de revisión requiere permiso específico y sesión vigente. Enviar una prueba requiere ese permiso y destinatario de prueba permitido; queda marcada en auditoría y fuera de métricas de producción.
4. El operador ve totales aprobados, en cola, suprimidos, aceptados, confirmados, inciertos y fallidos. Puede abrir el historial por destinatario bajo permiso, pausar, continuar o cancelar. Publicar recuentos agregados y motivos acotados para evitar duplicar direcciones o cuerpos en logs.

## Estado, persistencia y API

| Estado de campaña | Transiciones y efecto |
| --- | --- |
| `draft` | Edición y previsualización. Al aprobar, inmoviliza versión y audiencia. |
| `approved` | `scheduled` para una hora futura o `running` dentro de ventana. Nueva revisión tras una edición material. |
| `scheduled` | El worker habilita `running` a la hora acordada y con ruta de envío válida. `paused` o `cancelled` por operador. |
| `running` | Reclama trabajos elegibles. `paused` o `cancelled` corta nuevas autorizaciones. `completed` al cerrar todos los trabajos sin reintentos pendientes, con incidencias explícitas. `failed` para fallo de ejecución que requiere intervención. |
| `paused` | El operador revalida aprobación, proveedor y ventanas para reanudar. Si se reanuda fuera de ventana pasa a `scheduled`. También puede cancelar. |
| `completed`, `cancelled`, `failed` | Conservar historial. `cancelled` termina trabajo aún no autorizado. Los trabajos con llamada iniciada pueden recibir evidencia posterior. Una campaña `failed` puede reprocesar solo trabajo elegible a través de una operación privilegiada y auditable con la misma clave de envío. |

El modelo vive en el schema tenant de Operational. Una transición utiliza versión esperada para desambiguar ediciones y acciones simultáneas.

| Tabla propuesta | Restricciones y finalidad |
| --- | --- |
| `message_template`, `template_version` | Unicidad de `(template_id, version)`, autoría, estado de revisión y referencia externa opcional. Versiones aprobadas inmutables. |
| `campaign`, `campaign_approval` | Referencian `template_version`, canal, propósito, conexión tenantizada, ventana y política de frecuencia. La aprobación vincula versión y snapshot. |
| `campaign_recipient` | Único por `(campaign_id, contact_point_id)` y dirección normalizada deduplicada dentro del snapshot. Guarda evidencia de elegibilidad en aprobación y estado operativo actual. Revalidar si cambia o se fusiona el punto de contacto. |
| `campaign_job`, `delivery_attempt` | Un trabajo lógico por destinatario, lease, intento, siguiente ejecución y clave estable. El intento vincula cuenta, ID de proveedor, resultado y marcas temporales. |
| `channel_event`, `suppression` | Deduplicación por `(provider_account_id, event_id)` en la frontera de recepción. Una supresión se aplica a la finalidad o al canal conforme a su razón, con evidencia y fecha. |

Extender el API v1 de Operational con lista y edición de plantillas, borrador de campaña, previsualización, aprobación, programación, pausa, reanudación, cancelación y resultados paginados. Separar permisos de edición, aprobación, despacho y lectura de resultados sensibles. Usar `409` para una versión obsoleta y estados incompatibles y `422` para proveedor, plantilla o ventana inválidos. Contratos y nombres son propuestas y deben validarse antes de integrarlos. [Contrato de trabajos](../../../flowkron-api-contracts/schemas/jobs/async-job.schema.json)

## Gate de envío, idempotencia y recuperación

1. Confirmar tenant activo, campaña ejecutable, remitente vinculado, consentimiento vigente para canal y finalidad, supresión y frecuencia. Presencia, verificación de un email o conversación inbound por sí solas no habilitan campañas. BAJA, queja o rebote duro bloquean nuevos permisos en el alcance correspondiente.
2. Reservar el permiso de envío bajo el mismo orden de concurrencia que la actualización de consentimiento y la pausa. Un permiso posterior a BAJA devuelve `suppressed`. Los envíos autorizados antes de BAJA se concilian con evidencia sin recrear trabajo. El worker calcula ventanas locales con zona IANA, ajusta al próximo instante válido y usa cuotas separadas para tenant, proveedor y contacto. Reducir concurrencia al recibir señales de saturación y proteger atención inbound con capacidad propia.
3. Registrar estado `sending` durable antes de la llamada. Usar una clave de proveedor derivada del trabajo lógico, nunca del intento. Reintentar fallos transitorios con backoff y jitter, fecha límite y número de intentos acotados. Usar el reintento automático solo mientras la semántica de no duplicación del proveedor cubra la operación. Para Resend la documentación indica una ventana de 24 horas de idempotencia. [Idempotencia en Resend](https://resend.com/changelog/idempotency-keys)
4. Cuando no se pueda determinar el resultado, pasar a `unknown`. La recuperación consulta un estado externo o espera un recibo firmado y correlacionado. Una vez vencida la ventana de idempotencia, la resolución manual requiere evidencia de que el envío previo no fue aceptado. Al reanudar tras reinicio, reclamar trabajos disponibles por lease y conservar resultados ya aceptados o terminales.
5. Todas las bajas se registran de forma durable mediante enlace acotado a la finalidad o el mecanismo del canal. La respuesta es genérica e idempotente. La baja se refleja en segmentos, vista previa y siguiente intento. Conservar la evidencia mínima necesaria para evitar reapertura por importación o fusión. Los cambios de consentimiento conservan fuente, hora y versión de política.

## Evidencia y métricas

La respuesta de transporte crea evidencia `accepted` al devolver un ID de proveedor. El estado `delivered` requiere un recibo compatible y verificable con la cuenta y el envío. Para email representa aceptación del servidor receptor. Un rebote, queja y baja se registran por separado, incluso cuando llegan tras la confirmación. Un recibo duplicado no cambia conteos. Una transición tardía puede incorporar evidencia nueva sin revertir un estado confirmado por uno preliminar. Si faltan evidencias, mostrar `unknown` o `accepted` según lo observado. [Estados de entrega de Resend](https://resend.com/guides/email/users-never-got-login-code)

Los KPIs propuestos cuentan destinatarios únicos por campaña y registran ventana, canal y cobertura individual de recibos. Mostrar elegibles/snapshot, aceptados/intentados, confirmados/aceptados, bajas/aceptados y fallos por clase, además de la edad de trabajos sin resolución. Registrar respuestas solo cuando exista correlación verificable. Aperturas y clics quedan fuera del mínimo; si se habilitan, requieren observabilidad y política de privacidad específica y se explican sus limitaciones como señales de interacción. [Eventos de webhooks en Resend](https://resend.com/features/webhooks)

## Pruebas y secuencia de entrega

| Gate | Caso verificable con stub o sandbox autorizado |
| --- | --- |
| Elegibilidad | Contacto con canal sin opt-in queda excluido. BAJA entre aprobación y envío, durante reintento y durante pausa impide nuevas autorizaciones. Un usuario de otra empresa no accede al snapshot ni a la aprobación. |
| Aprobación | Cambiar variables, plantilla, remitente o segmento revoca aprobación. La vista previa escapa HTML y el dispatcher respeta permisos y zona, incluidos cambios de hora. |
| Entrega | Dos workers reclaman el mismo trabajo y solo uno obtiene permiso. Reinicio antes y después de la llamada, 429, timeout y expiración de idempotencia conservan estados y evitan retransmisión incierta. |
| Recibos | Firma inválida, repetición, cuenta ajena y eventos fuera de orden no contaminan el historial. Aceptado, entregado, rebote, baja y respuesta quedan distinguibles. |
| Canal | Demo usa exclusivamente stub. Email verifica remitente, entrega y baja en sandbox. WhatsApp real requiere además integración autorizada y evidencia de plantilla/consentimiento. Con una capacidad ausente, el envío real de ese canal se mantiene deshabilitado. |

Reutilizar FK-04 para decisión de consentimiento, FK-03 para invariantes de cola, FK-10/11 para eventos, FK-12/24 para credenciales y conexiones, FK-14 para adaptadores y FK-23 para integración de correo. La consolidación asignará la parte de plantillas y campañas que exceda estos IDs. Segmentación avanzada en tiempo de envío, automatizaciones multietapa y atribución se dejan para POST-v1. [Roadmap vigente](../../../EVOLUCION_FLOWKRON.md)
