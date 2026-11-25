# FK-02: turnos WhatsApp recuperables

Implementado el 18 de noviembre de 2026. Validado con PostgreSQL temporal y transporte simulado; no aplicado a una base existente ni a una cuenta real.

## Recorrido y propietarios

Operational guarda cada nueva entrada del conector y su `whatsapp_turns` en una misma transacción. La tabla usa como clave primaria el ID del mensaje de `mensajes_dashboard` y referencia el lead y la conversación del mismo schema autenticado. No crea un segundo historial de mensajes. El endpoint anterior `/message` sigue disponible para adaptadores existentes, con su deduplicación, sin crear automáticamente turnos.

El conector reclama el turno, consulta Agent Core si falta respuesta, persiste esa respuesta y la derivación humana, obtiene un permiso de envío y transmite el texto. Finalmente registra el ID real del proveedor. Solo se confirma envío aceptado (`sent`); no se presupone entrega o lectura.

| Estado persistido | Significado y recuperación |
| --- | --- |
| `received` | Entrada registrada; puede reclamarse para generación |
| `generating` | Una invocación tiene un lease de 180 segundos; al vencer se puede reclamar de nuevo |
| `prepared` | Respuesta inmutable y handoff guardados juntos; un reintento reutiliza el texto |
| `sending` | Se concedió un único intento de envío. No se concede otro aunque se pierda la respuesta HTTP del permiso |
| `completed` | Salida, marcador idempotente y resultado del proveedor guardados juntos; no vuelve a enviar |
| `unknown` | El envío pudo haber ocurrido; queda bloqueado para reenvío automático hasta recibir evidencia del canal o una reconciliación |
| `cancelled` | Se retiró consentimiento antes de generar/preparar/iniciar envío; no se reactiva por un reintento |

`legacy_untracked` es un resultado de API, no una fila nueva: el mensaje ya existía sin turno. No es seguro asumir que nunca se envió una respuesta, así que el conector no lo reproduce automáticamente. Tampoco se reconstruyen turnos de mensajes históricos al migrar.

## Coordinación y atomicidad

Reclamación y cambios de estado bloquean la fila del turno con `FOR UPDATE`. La reclamación devuelve un token aleatorio distinto por lease, que solo se entrega al propietario; consulta, duplicados y respuestas sin reclamación no lo revelan. Un token anterior no permite preparar ni enviar cuando otra invocación ya reclamó el turno. El lease se comprueba antes de las transiciones. Los procesos deben tener relojes sincronizados.

Las llamadas al agente y al canal ocurren fuera de las transacciones de Operational. `prepare` conserva el texto antes del efecto externo. La misma preparación repetida es idempotente; intentar cambiar sus argumentos devuelve 409. El handoff modifica el lead y registra su evento dentro de esa preparación, sin invocar por separado el endpoint anterior de handoff.

`begin-send` es deliberadamente de un solo uso. Si su respuesta se pierde, el conector no sabe si obtuvo permiso: marca/espera un resultado desconocido y no transmite a ciegas. Un envío con excepción o sin ID del proveedor también pasa a `unknown`. Es una estrategia conservadora: puede dejar un turno para revisión aun cuando el canal no haya enviado nada.

Una confirmación exitosa registra la salida con ID idempotente `flowkron:turn:<id>:reply` y su propio ID del proveedor. Si falla la persistencia después de enviar, el conector reintenta únicamente `complete`, hasta tres veces, con el mismo ID y fecha. Un fallo SQL revierte salida, marcador y finalización juntos. Una confirmación repetida devuelve el mensaje original; una confirmación con otro ID se rechaza.

La generación y preparación recuperables tienen hasta tres intentos por invocación, con espera acotada. La respuesta preparada se conserva. `release` libera un lease de generación/preparación, pero jamás devuelve un envío iniciado a `prepared`. Si el proceso desaparece durante `sending`, al vencer el lease una consulta o reclamación materializa `unknown`.

## Retirada de consentimiento

La primera entrega de FK-04 registra la BAJA y cancela en la misma transacción los turnos del contacto en `received`, `generating` y `prepared`. El alta de un turno nuevo comparte el bloqueo por contacto de la retirada y exige consentimiento vigente. El cambio de decisión registra fecha en `system_events`, identificador interno del contacto y los metadatos disponibles de canal y política. Repetir BAJA conserva el resultado. Un nuevo ACEPTO actualiza la fecha de concesión y permite consultas nuevas. Los turnos cancelados siguen siendo terminales tras un reinicio.

El conector impide el envío ordinario para ese número desde que admite la orden BAJA en la cola local. Si está esperando al agente, libera el turno antes de solicitar el permiso de envío. Si ya solicitó el permiso y recibe BAJA mientras espera la respuesta, evita la llamada al proveedor. El permiso eventualmente concedido sigue las reglas de `unknown`. Una baja que llega por otra instancia o directamente a la API se coordina hasta la concesión del permiso de envío en Operational. Después de ese punto, el remitente puede finalizar el único intento autorizado y registrar su recibo.

El conector de empresa admite una escritura de consentimiento y un trabajo ordinario en paralelo por sesión. BAJA tiene capacidad reservada y puede persistirse mientras el agente está ocupado. Mientras se procesa, bloquea envíos ordinarios para ese contacto. Conserva comandos pendientes con una fecha de proveedor posterior y desplaza los del mismo contacto que hayan quedado superados. Los acuses de WhatsApp pasan por la cola de salida ordinaria después de guardar la decisión.

`POST /api/v1/ingest/whatsapp/consent` acepta opcionalmente el `external_message_id` estable del comando. En la misma transacción guarda la decisión, las cancelaciones que correspondan y un marcador derivado de la identidad del contacto y del mensaje. Una repetición devuelve `duplicate: true` y la decisión vigente. El conector omite el acuse de una repetición, incluso si el primer resultado HTTP se perdió. Los clientes sin identificador mantienen la actualización directa. Actualizar Operational antes del conector para que los reintentos utilicen los marcadores desde la primera entrega.

Con `sent_at` y el identificador estable del comando, Operational ordena las decisiones entregadas fuera de orden. Solo las credenciales del puente pueden aportar la hora del proveedor. La precisión es de un segundo, BAJA prevalece si ambas decisiones empatan y las fechas futuras se limitan a la hora actual del servicio. Una entrega tardía deja la decisión vigente y devuelve `stale: true`. Si una BAJA tardía cierra un período previo a un ACEPTO posterior, cancela los trabajos recuperables anteriores a esa renovación y rechaza nuevas admisiones que lleguen desde ese período. El conector omite el acuse de comandos obsoletos.

Las actualizaciones directas conservan la hora del servidor como límite de orden. La actualización genérica de un contacto existente conserva su consentimiento cuando la petición omite el campo. La garantía de un comando empieza con el commit de Operational. Una caída anterior a ese punto todavía puede perder un comando que solo esté en memoria.

## Cola durable de turnos

El conector de empresa admite consultas con consentimiento mediante `POST /turns/enqueue`. Una sola transacción guarda la entrada, el turno y un trabajo que conserva la clave de la cuenta conectada y el destinatario original. `202 accepted` confirma esa transacción. `duplicate` indica que ya existe trabajo para ese mensaje. `legacy_untracked` conserva el recorrido anterior por reentrega y excluye el mensaje del barrido automático. Los comandos ACEPTO y BAJA entran por la ruta de consentimiento.

Desde que abre o restaura el socket, el conector consulta `POST /turns/next` para su cuenta. Operational serializa reclamación y admisión de la empresa con transacciones cortas, evita filas bloqueadas y usa el lease existente. Atiende primero el turno disponible más antiguo y espera las reclamaciones activas del mismo contacto. Otras conversaciones pueden avanzar mientras una espera su próximo intento. La cuenta se deriva del ID normalizado de WhatsApp sin el sufijo del dispositivo. Volver a vincular otra cuenta no reasigna los trabajos antiguos.

Hay capacidad para 128 trabajos activos por empresa. Una consulta nueva ante saturación recibe 429 y se puede volver a presentar con el mismo ID. Los duplicados conservan su resultado aunque la cola esté llena. Cada turno tiene cinco reclamaciones automáticas y las liberaciones recuperables esperan de 5 a 80 segundos. Los turnos agotados liberan capacidad cuando finaliza su lease. El envío al proveedor espera hasta 60 segundos por un acuse. Si se agota esa espera o se vence un lease en `sending`, el turno pasa a `unknown` y queda sujeto a reconciliación.

Para reprogramar un trabajo agotado con estado recuperable, verificar el consentimiento y la cuenta original, y usar `POST /turns/{turn_id}/retry` con `account_key` mediante credenciales privadas de la empresa. Se registra el evento `whatsapp.turn.requeued`, se verifica capacidad y se reinician intentos. El worker vuelve a reclamar el trabajo por su camino habitual. Una respuesta preparada se conserva. El reintento controlado excluye envíos inciertos, cancelados y completados.

La admisión durable empieza con el commit. La normalización, las consultas previas de consentimiento, los mensajes todavía en la cola del conector y los acuses de consentimiento permanecen fuera de esa garantía. Un error de admisión queda en el límite del conector, que registra el fallo y permite una reentrega del proveedor.

## API y credenciales

Prefijo `/api/v1/ingest/whatsapp/turns`. Usa el mecanismo existente de ingestión por empresa: `X-Flowkron-Tenant` + `X-Baileys-Token`, o `X-Tenant-Code` + `X-Ingest-Key`, runtime activo y límites de admisión/tasa existentes. No acepta `schema_name` ni usa el JWT del navegador. Las respuestas usan envelope estándar y `Cache-Control: no-store` en éxito.

| Método y sufijo | Entrada | Efecto |
| --- | --- | --- |
| `POST /claim` | Mensaje entrante, compatible con campos de FK-01 | Guardar entrada nueva con consentimiento vigente y reclamar si procede; devuelve entrada persistida y respuesta guardada |
| `POST /enqueue` | Mensaje entrante, clave de cuenta y destinatario del proveedor | Admisión atómica de consulta con consentimiento |
| `POST /next` | Clave de cuenta | Reclamar trabajo disponible o devolver `job: null` |
| `POST /{turn_id}/retry` | Clave de cuenta | Reprogramar un turno recuperable que agotó intentos |
| `GET /{turn_id}` | ID del turno | Consultar diagnóstico; materializa incertidumbre si venció un envío |
| `POST /{turn_id}/prepare` | Token, texto y `requires_human` | Persistir respuesta y handoff atómicamente |
| `POST /{turn_id}/begin-send` | Token y reserva opcional del ID del proveedor | Autorizar solo la primera transición a envío |
| `POST /{turn_id}/complete` | Token, ID del proveedor y fecha con zona | Finalizar; idempotente para el mismo ID |
| `POST /{turn_id}/release` | Token | Liberar una etapa segura o señalar envío desconocido |
| `POST /{turn_id}/reconcile` | ID y fecha del envío externamente comprobados | Resolver incertidumbre sin transmitir ni necesitar el token de un proceso que ya terminó |

Errores relevantes: 401 por credenciales inválidas, 403 por runtime suspendido o entrada nueva sin consentimiento, 404 por recurso ausente, 409 por estado/token/identidad incompatible, 422 por argumentos y 429 por límites. Cada paso cuenta contra la tasa de ingestión; dimensionar esa tasa considerando el recorrido completo, no solo mensajes entrantes.

## Recibos del proveedor

En el recorrido durable, el conector genera el ID que Baileys usará al transmitir. Operational lo reserva al conceder el permiso de envío. El conector reporta eventos directos de salida desde `messages.update` a `POST /api/v1/ingest/whatsapp/receipts` con sus credenciales de puente. Operational exige coincidencia de empresa, conexión, cuenta, ID y destinatario. Las respuestas de consentimiento, los grupos y el historial sin reserva quedan fuera de este recorrido.

La evidencia avanza en este orden: envío aceptado, fallo reportado, entrega y lectura. Los duplicados y estados anteriores se omiten. Una entrega comprobada puede corregir un fallo reportado previamente. Se conservan motivos normalizados como cuenta restringida o conexión inválida. El texto y las estructuras internas del error del proveedor quedan fuera del registro.

Un evento coincidente puede cerrar un turno `sending` o `unknown` incluso antes de que retorne la llamada de envío. Si llega primero el recibo, la fila de salida usa la hora del permiso como referencia del intento. La confirmación posterior con el mismo ID conserva esa fila. Los intentos inciertos sin evidencia siguen el procedimiento de reconciliación.

El conector reúne hasta 32 recibos por solicitud y mantiene una cola en memoria con capacidad y reintentos acotados. La garantía empieza al guardar la evidencia en Operational. Cuando se pierde un evento antes de ese punto, el CRM conserva el último estado comprobado. La lectura compartida del inbox es un dato de operación del CRM y tiene su propio contador.

## Reconciliación operativa

1. Consultar el turno con credenciales privadas de su empresa; conservar su ID para diagnóstico.
2. Si está `sending` y su lease sigue activo, esperar o investigar al proceso original. No registrar una reconciliación concurrente: se rechaza.
3. En `unknown`, verificar externamente el envío original, su destinatario, texto, ID y fecha. Esta versión no busca automáticamente en el proveedor ni acredita evidencia solo porque un operador aporte un ID.
4. Si se comprobó que fue enviado, usar `reconcile` con ese ID y fecha. Se registra `whatsapp.turn.reconciled` y se guarda una sola salida; el endpoint nunca envía mensajes.
5. Si no hay evidencia suficiente, mantener `unknown`. No inventar un ID ni resetear directamente la tabla para reenviar. No se incorpora una operación automática para declarar «no enviado» o forzar reenvío.

El token del lease no es un token de usuario y no debe imprimirse ni almacenarse en logs. Las credenciales de ingestión ya otorgan escritura de la empresa; esta operación es de mantenimiento privado, no un botón de cliente expuesto al navegador. Una futura UI autorizada debe pasar por su API con permisos y actor auditable (FK-09/FK-18).

## Migración y compatibilidad

`tenant_schema_v4` agrega `whatsapp_turns` al conjunto activo. `apply_tenant_schema` conserva la migración FK-01 y crea la nueva tabla para empresas nuevas y existentes; no altera la migración anterior ni infiere trabajo histórico. Actualizar el valor si una instalación fija `TENANT_MIGRATION_VERSION`; cambiar solo la etiqueta no ejecuta la migración.

`tenant_schema_v5` agrega `whatsapp_turn_jobs`; la tabla apunta a los turnos ya existentes por una clave foránea y solamente se puebla en las nuevas admisiones durables. `tenant_schema_v7` incorpora las reservas para recibos. `tenant_schema_v8` agrega el orden de decisiones de consentimiento y recupera el último límite temporal registrado desde auditoría cuando hay evidencia histórica. Actualizar Operational y migrar la empresa a v8 antes de actualizar el conector.

Para una instalación existente: backup/restauración ensayados, pausa de tráfico del conector, migración autorizada con la herramienta existente y revisión por schema. El recorrido masivo solo incluye runtimes activos; tratar los suspendidos mediante mantenimiento antes de reactivarlos. Desplegar Operational compatible antes de reabrir el conector nuevo. No mezclar consumidores antiguos y nuevos del mismo canal durante la transición.

Rollback: conservar la tabla y sus evidencias; no borrar turnos o reiniciar marcadores. Pausar tráfico y revisar los turnos no completados antes de volver a un conector anterior, porque ese código no entiende sus etapas. El rollback de DDL fallido sigue siendo transaccional. La actualización de binarios no prueba compatibilidad operativa con trabajos que ya estaban en curso.

## Límites y validación

- El barrido de FK-03 incluye los turnos admitidos en v5. Los turnos v4 y los casos históricos siguen su recorrido previo de reentrega o reconciliación.
- `unknown` es visible en API de ingestión y DB; el CRM aún no tiene una vista de diagnóstico de turnos. No hay ejecución de correo, agenda u otras herramientas externas.
- Las pruebas de FK-02 ejercitan PostgreSQL, concurrencia, rollback y API ASGI real con credenciales, validación y envelopes. El conector inyecta fallos de generación, preparación, permiso, envío y persistencia. No se requieren cuentas reales ni dependencias nuevas.
- La suite previa basada en `TestClient` conserva su problema de dependencias; las pruebas HTTP nuevas usan ASGI directamente. No se declara aprobada toda la suite ni CI remoto a partir de estas verificaciones.
