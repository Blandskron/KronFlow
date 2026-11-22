# CRM, captación inbound y atención humano-IA

**Estado:** especificación propuesta. Parte de la [auditoría](01-audit.md) y el [ADR de módulos](02-architecture-adrs.md). Aplica a los flujos de una empresa activa con datos sintéticos en demo.

## Recorrido principal

1. Un visitante envía un formulario de una empresa o inicia una conversación por WhatsApp. Operational resuelve tenant, origen y canal desde la integración y valida el payload. El adaptador WhatsApp aplica su gate de privacidad y consentimiento vigente para atención.
2. Operational registra una captura idempotente. Busca el contacto por un punto normalizado del mismo tenant. Si no coincide, crea un contacto y un lead. Si los identificadores apuntan a contactos distintos, registra un conflicto para revisión sin fusionarlos ni exponer coincidencias. Conserva el origen y el vínculo con el formulario o mensaje.
3. El lead aparece en el CRM. Cuando hay una conversación habilitada para IA, Operational encola un turno y Agent Core recibe solo el contexto necesario. Si la IA solicita atención humana o el equipo toma control, el inbox muestra el motivo y la nueva asignación.
4. Un operador autorizado reclama y responde por una conexión habilitada. Puede resolver el hilo o devolver el control a IA. El operador puede crear una oportunidad desde el contacto o lead y vincularla con la conversación.
5. El responsable mueve la oportunidad de etapa, registra actividades y cierra como ganada o perdida. El historial comercial y la atención tienen estados independientes y se pueden consultar desde el contacto.

La landing actual persiste consultas institucionales mediante `ContactMessageView`. `/app/workflows` agrupa conversaciones y la API de leads ya permite lectura y edición. El nuevo recorrido conserva el flujo institucional y agrega puntos de entrada de captación de empresa. [Formulario actual](../../../flowkron-auth-service/apps/contact/views.py) · [API leads](../../../flowkron-operational-service/app/api/v1/leads.py) · [Vista de seguimiento](../../../flowkron-front-app-angular/src/app/domains/leads/features/workflows-page/workflows-page.component.ts)

## Modelo y propietarios

| Entidad | Datos y reglas |
| --- | --- |
| `Cliente` y `contact_point` · Operational | Identidad canónica en `Cliente`. Puntos con tipo, valor normalizado, estado, verificación y fecha, más etiqueta de uso. Unicidad de identidad normalizada dentro del tenant donde sea válido reclamarla. Guardar origen, responsable y actividad referenciada. Verificar antes de usar un dato cuando el canal o la acción lo requiera. |
| `consent_decision` · Operational | Historial y proyección vigente por punto de contacto, canal y finalidad. Registra decisión, fuente, política, actor y momento efectivo. `consentimiento_datos` existente se interpreta en su contexto de WhatsApp. El backfill conserva evidencia disponible y deja marketing sin autorización hasta contar con evidencia explícita. |
| `lead_capture` y `Lead` · Operational | Guarda origen, identificador externo, huella de payload, referencia a lead y estado de validación. Si varias capturas aportan el mismo contacto, preservar sus orígenes. Determinar lead abierto reutilizable bajo llave de negocio definida por tenant. |
| `contact_tag`, `contact_group` · Operational | Etiquetas y listas estáticas para el mínimo v1 de segmentación. Listas dinámicas expresadas con filtros tipados de campos permitidos como etapa, etiqueta u origen. Paginación SQL con orden total y desempate por ID. |
| `Conversation`, control e historial · Operational | Mantiene sesión, canal y mensajes existentes. Agrega modo, propietario humano, versión monotónica y auditoría de control. Consentimiento de contacto y derecho a enviar siguen evaluándose por separado. |
| `pipeline_stage`, `opportunity`, `opportunity_activity` · Operational | Un pipeline editable por tenant, etapas ordenadas, responsable, importe decimal y moneda ISO, resultado y motivo al cerrar. La oportunidad tiene vínculo explícito con el contacto y opcional con lead y conversación. Actualizaciones de etapa escriben evento en la misma transacción. |
| `Form` y credencial privada · Operational/IAM | Operational configura campos permitidos y referencia de origen. IAM emite, rota y revoca credenciales acotadas. Operational resuelve alcance y tenant en cada solicitud de captación. |

Antes de migrar, perfilar duplicados con datos anonimizados en una copia autorizada. Poblar puntos inequívocos de `Cliente` de forma aditiva y conservar IDs usados por leads y conversaciones. Para teléfono usar E.164 cuando exista región o prefijo confiable y preservar la identidad previa del canal. Para correo evitar supuestos sobre variantes de alias y mayúsculas de la parte local. Una fusión registra origen, destino, actor, motivo y reasignaciones transaccionales. Mantiene auditoría y enlaces de los dos IDs, y conserva la supresión más restrictiva para las finalidades afectadas.

## Captación y contratos propuestos

| Operación | Credencial, comportamiento y respuesta |
| --- | --- |
| `POST /api/v1/integrations/leads` | Clave servidor a servidor con `leads:create`. IAM vincula empresa e integración, guarda hash, fecha de expiración e historial de rotación y revocación. Operational verifica el ámbito y el estado, limita por credencial y exige una clave idempotente. Retorna `202` y captura opaca. |
| `POST /api/v1/forms/{form_token}/submissions` | Identificador público rotatorio vinculado al formulario. Aplicar validación de esquema, máximo de body/campos, cuotas por origen y formulario, honeypot y challenge optativo ante abuso. La validación de origen complementa las cuotas. Una captura válida responde `202` con texto genérico y sin IDs de contacto ni señales de existencia. |
| `GET /api/v1/contacts`, `GET/PATCH /contacts/{id}` | Lectura de CRM por tenant y edición con `crm.manage` como base. Filtros por punto de contacto, etiqueta, origen o responsable y paginación SQL. Solo la gestión autorizada puede ver o modificar el consentimiento, con registro de evidencia. |
| `POST /api/v1/conversations/{id}/claim`, `/messages`, `/return-to-ai`, `/resolve` | Autorización específica por acción y por conversación. Idempotencia para mensajes y versión esperada para transición. El envío manual responde `202` con estado en cola. El remitente se resuelve desde la conexión del tenant. |
| `GET/POST /api/v1/opportunities`, `PATCH /opportunities/{id}` | Filtra por tenant, etapa y responsable. Edición con permiso comercial y precondición de versión. Un cambio válido persiste etapa, resultado e historial atómicamente. |

Usar el envelope y metadata de tenant de Operational. Validar tamaños, campos y tipos antes de escribir. El registro de idempotencia privado usa `(integración, idempotency_key)` y huella del payload normalizado. El reintento idéntico devuelve el ID de captura original. Un payload diferente con la misma clave privada devuelve `409`. El formulario público mantiene la misma forma de respuesta para la aceptación repetida y limita reenvíos sin revelar si existía contacto. En el formulario incrustado, el cliente recibe únicamente el token de formulario. Comprobar origen del consentimiento y política presentada, con controles explícitos para finalidades comerciales opcionales. Captación confirma recepción y deja marketing desactivado por defecto. Si una integración requiere webhook saliente, reutilizar FK-10/11, con firma, deduplicación y propósito acotado.

Para importación CSV, usar validación previa y un lote con resumen de errores por fila. Fijar encabezados permitidos, codificación y límites de tamaño. Importar en transacciones acotadas con idempotencia por lote y fila. La exportación requiere permiso separado, conserva filtros de tenant y neutraliza celdas interpretables como fórmulas. Registrar quién exporta, fecha y número de registros. La vista previa y exportación quedan como SHOULD si la entrega mínima necesita solo formulario y captura por canal.

## Control de conversación

| Transición propuesta | Actor y efecto |
| --- | --- |
| `ai_active → waiting_human` | Agente emite propuesta de handoff o un operador solicita atención. Se registra motivo y se impide conceder nuevos permisos de IA. |
| `ai_active` o `waiting_human → human_active` | Operador autorizado reclama la conversación. Una operación compare-and-swap decide al ganador si dos operadores reclaman. La transferencia conserva historial. |
| `human_active → ai_active` | Responsable humano o supervisor devuelve control. Requiere IA habilitada, consentimiento vigente y una conexión apta. Arranca bajo una versión de control nueva. |
| `human_active → resolved` | Operador autorizado resuelve con motivo. Una entrada posterior aplica la política de reapertura auditada y vigente del tenant. |

Un worker revalida estado, versión, permiso aplicable, consentimiento y runtime inmediatamente antes del permiso de envío. Las transiciones invalidan trabajos de IA pendientes de autorización. Si una solicitud al proveedor ya fue autorizada, conservar su evidencia y mostrar su estado hasta confirmar o reconciliar; la escalada evita conceder permisos nuevos. El alcance de escritura incluye responsable actual o supervisor. Las propuestas de herramientas registran tipo, argumentos validados, recursos, expiración, actor y correlación. La aprobación humana queda asociada a una versión concreta y una ejecución idempotente vuelve a autorizar el recurso. Limitar memoria a datos relevantes para el caso, conservar vínculos a su origen y aplicar retención tenantizada. [Turnos recuperables](../../../flowkron-operational-service/docs/TURN_RECOVERY.md)

## Evidencia de aceptación y alcance

| Prioridad | Caso E2E verificable |
| --- | --- |
| MUST · identidad y captación | Enviar dos veces el mismo payload, observar una captura y un lead. Repetir con otra empresa y observar su recurso independiente. Probar token revocado, formulario inválido y abuso sin enumerar contactos. |
| MUST · consentimiento y handoff | Cargar una conversación sintética, escalar a un humano mientras la generación está bloqueada y comprobar un solo operador activo y cero nuevos permisos de IA. Responder con proveedor stub. Tras BAJA, comprobar cancelación según propósito y que volver a otorgar consentimiento solo habilita nuevos trabajos. |
| MUST · oportunidad | Desde un lead crear una oportunidad, moverla de etapa y cerrar con resultado. La oportunidad y su historial sobreviven al reinicio y un actor de otra empresa no puede leerla ni mutarla. |
| MUST · acciones de IA | Probar que un dato propuesto no modifica el CRM hasta que se confirme y autorice. Repetir la ejecución de una aprobación y verificar un solo efecto por ID. |
| SHOULD | Fusionar con auditoría, importar/exportar por lotes, segmentos dinámicos, aprobaciones avanzadas y seguimiento comercial básico. |
| POST-v1 | Múltiples pipelines por empresa, agenda avanzada y automatizaciones arbitrarias. |

Eventos candidatos para el catálogo: `lead.captured`, `contact.created`, `consent.changed`, `conversation.handoff_requested`, `conversation.claimed`, `conversation.control_changed`, `opportunity.stage_changed` y `opportunity.closed`. Los eventos llevan IDs, versión, hora y correlación con payload mínimo. Motivos de privacidad y notas libres se conservan en la fuente autorizada. FK-06/19 cubren control, FK-12 credenciales, FK-17/18/20/21 acciones, memoria y calidad de datos, y FK-25/27 supervisión y privacidad. Las brechas de directorio y pipeline se trasladan a la consolidación con trazabilidad al [roadmap vigente](../../../EVOLUCION_FLOWKRON.md).
