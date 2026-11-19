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
| `completed` | Salida, marcador idempotente y finalización guardados juntos; no vuelve a enviar |
| `unknown` | El envío pudo haber ocurrido; queda bloqueado para reenvío automático y requiere reconciliación |
| `cancelled` | Se retiró consentimiento antes de generar/preparar/iniciar envío; no se reactiva por un reintento |

`legacy_untracked` es un resultado de API, no una fila nueva: el mensaje ya existía sin turno. No es seguro asumir que nunca se envió una respuesta, así que el conector no lo reproduce automáticamente. Tampoco se reconstruyen turnos de mensajes históricos al migrar.

## Coordinación y atomicidad

Reclamación y cambios de estado bloquean la fila del turno con `FOR UPDATE`. La reclamación devuelve un token aleatorio distinto por lease, que solo se entrega al propietario; consulta, duplicados y respuestas sin reclamación no lo revelan. Un token anterior no permite preparar ni enviar cuando otra invocación ya reclamó el turno. El lease se comprueba antes de las transiciones. Los procesos deben tener relojes sincronizados.

Las llamadas al agente y al canal ocurren fuera de las transacciones de Operational. `prepare` conserva el texto antes del efecto externo. La misma preparación repetida es idempotente; intentar cambiar sus argumentos devuelve 409. El handoff modifica el lead y registra su evento dentro de esa preparación, sin invocar por separado el endpoint anterior de handoff.

`begin-send` es deliberadamente de un solo uso. Si su respuesta se pierde, el conector no sabe si obtuvo permiso: marca/espera un resultado desconocido y no transmite a ciegas. Un envío con excepción o sin ID del proveedor también pasa a `unknown`. Es una estrategia conservadora: puede dejar un turno para revisión aun cuando el canal no haya enviado nada.

Una confirmación exitosa registra la salida con ID idempotente `flowkron:turn:<id>:reply` y su propio ID del proveedor. Si falla la persistencia después de enviar, el conector reintenta únicamente `complete`, hasta tres veces, con el mismo ID y fecha. Un fallo SQL revierte salida, marcador y finalización juntos. Una confirmación repetida devuelve el mensaje original; una confirmación con otro ID se rechaza.

La generación y preparación recuperables tienen hasta tres intentos por invocación, con espera acotada. La respuesta preparada se conserva. `release` libera un lease de generación/preparación, pero jamás devuelve un envío iniciado a `prepared`. Si el proceso desaparece durante `sending`, al vencer el lease una consulta o reclamación materializa `unknown`.

## API y credenciales

Prefijo `/api/v1/ingest/whatsapp/turns`. Usa el mecanismo existente de ingestión por empresa: `X-Flowkron-Tenant` + `X-Baileys-Token`, o `X-Tenant-Code` + `X-Ingest-Key`, runtime activo y límites de admisión/tasa existentes. No acepta `schema_name` ni usa el JWT del navegador. Las respuestas usan envelope estándar y `Cache-Control: no-store` en éxito.

| Método y sufijo | Entrada | Efecto |
| --- | --- | --- |
| `POST /claim` | Mensaje entrante, compatible con campos de FK-01 | Guardar entrada/turno y reclamar si procede; devuelve entrada persistida y respuesta guardada |
| `GET /{turn_id}` | ID del turno | Consultar diagnóstico; materializa incertidumbre si venció un envío |
| `POST /{turn_id}/prepare` | Token, texto y `requires_human` | Persistir respuesta y handoff atómicamente |
| `POST /{turn_id}/begin-send` | Token | Autorizar solo la primera transición a envío |
| `POST /{turn_id}/complete` | Token, ID del proveedor y fecha con zona | Finalizar; idempotente para el mismo ID |
| `POST /{turn_id}/release` | Token | Liberar una etapa segura o señalar envío desconocido |
| `POST /{turn_id}/reconcile` | ID y fecha del envío externamente comprobados | Resolver incertidumbre sin transmitir ni necesitar el token de un proceso que ya terminó |

Errores relevantes: 401 por credenciales inválidas, 403 por runtime suspendido, 404 por recurso ausente, 409 por estado/token/identidad incompatible, 422 por argumentos y 429 por límites. Cada paso cuenta contra la tasa de ingestión; dimensionar esa tasa considerando el recorrido completo, no solo mensajes entrantes.

## Reconciliación operativa

1. Consultar el turno con credenciales privadas de su empresa; conservar su ID para diagnóstico.
2. Si está `sending` y su lease sigue activo, esperar o investigar al proceso original. No registrar una reconciliación concurrente: se rechaza.
3. En `unknown`, verificar externamente el envío original, su destinatario, texto, ID y fecha. Esta versión no busca automáticamente en el proveedor ni acredita evidencia solo porque un operador aporte un ID.
4. Si se comprobó que fue enviado, usar `reconcile` con ese ID y fecha. Se registra `whatsapp.turn.reconciled` y se guarda una sola salida; el endpoint nunca envía mensajes.
5. Si no hay evidencia suficiente, mantener `unknown`. No inventar un ID ni resetear directamente la tabla para reenviar. No se incorpora una operación automática para declarar «no enviado» o forzar reenvío.

El token del lease no es un token de usuario y no debe imprimirse ni almacenarse en logs. Las credenciales de ingestión ya otorgan escritura de la empresa; esta operación es de mantenimiento privado, no un botón de cliente expuesto al navegador. Una futura UI autorizada debe pasar por su API con permisos y actor auditable (FK-09/FK-18).

## Migración y compatibilidad

`tenant_schema_v4` agrega `whatsapp_turns` al conjunto activo. `apply_tenant_schema` conserva la migración FK-01 y crea la nueva tabla para empresas nuevas y existentes; no altera la migración anterior ni infiere trabajo histórico. Actualizar el valor si una instalación fija `TENANT_MIGRATION_VERSION`; cambiar solo la etiqueta no ejecuta la migración.

Para una instalación existente: backup/restauración ensayados, pausa de tráfico del conector, migración autorizada con la herramienta existente y revisión por schema. El recorrido masivo solo incluye runtimes activos; tratar los suspendidos mediante mantenimiento antes de reactivarlos. Desplegar Operational compatible antes de reabrir el conector nuevo. No mezclar consumidores antiguos y nuevos del mismo canal durante la transición.

Rollback: conservar la tabla y sus evidencias; no borrar turnos o reiniciar marcadores. Pausar tráfico y revisar los turnos no completados antes de volver a un conector anterior, porque ese código no entiende sus etapas. El rollback de DDL fallido sigue siendo transaccional. La actualización de binarios no prueba compatibilidad operativa con trabajos que ya estaban en curso.

## Límites y validación

- FK-02 persiste etapas y admite reintentos; todavía no implementa cola durable, escáner de pendientes, recuperación automática al iniciar, heartbeats ni un scheduler. Tras agotar reintentos o perder una reclamación, se necesita una nueva entrega/reclamación; el barrido de pendientes corresponde a FK-03.
- Se revalida consentimiento al reclamar, preparar e iniciar envío. No se cancela retroactivamente una llamada al canal ya autorizada/iniciada; el tratamiento completo de retiradas concurrentes y su evidencia sigue en FK-04.
- `unknown` es visible en API de ingestión y DB; el CRM aún no tiene una vista de diagnóstico de turnos. No hay ejecución de correo, agenda u otras herramientas externas.
- Las pruebas de FK-02 ejercitan PostgreSQL, concurrencia, rollback y API ASGI real con credenciales, validación y envelopes. El conector inyecta fallos de generación, preparación, permiso, envío y persistencia. No se requieren cuentas reales ni dependencias nuevas.
- La suite previa basada en `TestClient` conserva su problema de dependencias; las pruebas HTTP nuevas usan ASGI directamente. No se declara aprobada toda la suite ni CI remoto a partir de estas verificaciones.
