# Eventos, métricas y observabilidad de Community v1

**Estado:** especificación propuesta. El primer ajuste de FK-09 alinea `open_conversations` y `requires_human` con los hilos de la Bandeja y mantiene los conteos de leads y mensajes en el schema tenant. FK-09 también verifica el tenant del envelope. Los KPIs de eventos de este documento requieren instrumentar sus fuentes. [Implementación actual](../../../flowkron-operational-service/app/services/analytics_service.py) · [Pruebas de Bandeja](../../../flowkron-operational-service/tests/test_conversation_inbox.py) · [Roadmap](../../../EVOLUCION_FLOWKRON.md)

La primera serie diaria está disponible en `/api/v1/analytics/activity`. Cuenta altas de contactos y leads y mensajes por dirección desde las tablas operacionales. El intervalo está acotado a 31 días, usa la zona IANA solicitada e indica el corte parcial. [Contrato de actividad](../../../flowkron-operational-service/docs/API.md#analytics)

Operational expone una proyección histórica versionada de eventos seleccionados en `/api/v1/operational/audit-events`. Usa transacciones de la auditoría ya persistida. Agent Core propaga el UUID de correlación a las llamadas internas de contexto. [Contrato y alcance](../../../flowkron-operational-service/docs/API.md#eventos-de-auditoría)

## Contratos y catálogo mínimo

Conservar el envelope `domain-event`: `event_id`, `event_type`, `event_version`, `occurred_at`, `producer`, `correlation_id`, `trace_id` y `data`. Para nuevos eventos operativos, exigir `tenant_id` resuelto en el productor. Guardar `recorded_at` en el registro persistido. Definir `resource_id`, `causation_id` y el actor mínimo (`kind` y referencia interna cuando haga falta) en el schema de `data` de cada tipo. El envelope vigente restringe propiedades adicionales. `async-job` representa el estado consultable de un trabajo y el evento registra la transición observada. [Evento](../../../flowkron-api-contracts/schemas/events/domain-event.schema.json) · [Trabajo](../../../flowkron-api-contracts/schemas/jobs/async-job.schema.json) · [ADR de eventos](../../../flowkron-api-contracts/docs/decisions/ADR-0004-event-contracts.md)

| Familia e IDs candidatos `v1` | Emisor y evidencia de origen | Campos de `data` y clave de deduplicación |
| --- | --- | --- |
| `contact.created`, `lead.captured` | Operational al confirmar el alta y la captura | ID de contacto/lead, fuente y canal. ID de creación o captura idempotente. |
| `message.accepted`, `message.delivered`, `message.failed` | Operational al persistir aceptación o aplicar evidencia del adaptador | ID de mensaje, canal, cuenta, campaña opcional y clase de resultado. ID de envío o evento confirmado por la cuenta. |
| `campaign.started`, `campaign.completed`, `consent.changed` | Control de campaña y registro de decisiones en Operational | ID de campaña o decisión, canal, finalidad, decisión y versión. Transición persistida o decisión idempotente. |
| `conversation.opened`, `conversation.handoff.requested`, `conversation.claimed`, `conversation.control.changed`, `conversation.resolved` | Control de conversación y mensajes entrantes de Operational | ID de conversación, versión, episodio de apertura, canal y motivo codificado. ID de transición. |
| `opportunity.stage.changed`, `opportunity.won`, `opportunity.lost` | Transacción de actualización comercial | ID de oportunidad, etapa, cantidad decimal, moneda y versión. ID de transición o cierre. |
| `agent.action.proposed`, `agent.action.approved`, `agent.action.executed` | Operational persiste propuesta, aprobación y ejecución con correlación a Agent Core | ID de acción, tipo de efecto, modo, resultado y versión. ID de transición. |
| `job.retried`, `job.finished`, `agent.usage.recorded` | Worker y consumidor de uso de Agent Core al confirmar evidencia | ID de trabajo e intento, clase de error, duración y modelo. Uso/coste solo con unidad, moneda, origen y valor declarado. ID de intento o medición. |

`occurred_at` refleja el instante del productor o la marca validada del proveedor. `recorded_at` indica recepción duradera. Los eventos tardíos actualizan ventanas anteriores según política publicada. Un recibo preliminar tardío no revierte evidencia terminal. Usar IDs opacos; conservar textos libres, emails, teléfonos, prompts, URLs firmadas y bodies en sus fuentes autorizadas.

## Diccionario de KPIs y reglas de consistencia

Cada lectura filtra por empresa autenticada. Cuando el dominio lo permite, filtra por canal y campaña; ventas agrupa por responsable y moneda. Las ventanas se declaran como `[inicio, fin)` con zona IANA del tenant y límites convertidos a UTC. Las tasas con denominador cero son `null`. El objetivo inicial es frescura p95 de 60 s y lectura p95 de 500 ms en el entorno de carga acordado. Ambos son metas sin medición aún. [ADR de arquitectura](02-architecture-adrs.md)

| Vista y KPI | Numerador, denominador y ancla | Evidencia, límite y control |
| --- | --- | --- |
| Dirección · contactos y leads nuevos | Contactos únicos de `contact.created` y capturas únicas de `lead.captured` ocurridas en la ventana. Conteos. | Un replay conserva ambos conteos. Un contacto puede tener varias capturas. |
| Marketing · entrega confirmada | Destinatarios con `message.delivered` / destinatarios `message.accepted`; cohorte por aceptación en la ventana, con corte `as_of` para recibos. | Cuenta y envío deben coincidir. Informar cobertura de eventos. Email confirma aceptación por servidor receptor. |
| Marketing · bajas de campaña | Bajas verificadas y correlacionadas por destinatario / aceptados de esa campaña; cohorte por fecha de aceptación. | Una baja sin correlación aporta al total de canal. Evitar asignar causalidad por mera coincidencia temporal. |
| Atención · conversaciones abiertas | Conversaciones con episodio activo a `as_of`, según estado de Operational. Conteo. | Dos conversaciones del mismo lead cuentan por separado. Comparar con la tabla de conversación, y no con el conteo legado de leads. |
| Atención · atención humana | Episodios reclamados / episodios con handoff durante la ventana, con `as_of`. Mediana/p95 desde handoff a claim entre episodios reclamados. | Cada episodio cuenta una vez y excluye los casos sin marca válida en cálculos de demora. Reportar pendientes. |
| Ventas · tasa de cierre e importe | Ganadas / (ganadas + perdidas) con cierre efectivo en la ventana. Suma de importes ganados por moneda. | Anclar al cierre vigente de cada oportunidad para el corte. Reaperturas se reconcilian mediante versión e historial. Sin conversión de moneda ni atribución implícita. |
| IA · acciones ejecutadas | Propuestas ejecutadas / propuestas registradas en la ventana, con corte. Desglose de aprobadas, rechazadas y expiradas cuando exista registro. | Vincular propuesta, decisión y ejecución por ID. La tasa mide flujo, no satisfacción ni calidad semántica. |
| IA · coste conocido | Suma cuantificada por moneda/modelo y número de invocaciones medidas / total de invocaciones en la ventana. | Sin imputar desconocidos. Mostrar cobertura y distinguir demo. |
| Operaciones · retraso y recuperación | p95 `recorded_at - occurred_at` para fuentes con hora fiable, edad de cola pendiente y trabajos con reintento / trabajos iniciados en la ventana. | Separar incidentes técnicos de eventos de negocio. Clasificar fallos de conexión y resultados inciertos. |

## Agregación, API y privacidad

1. Empezar con SQL tenantizado sobre estados fuente y contar solo los eventos que tengan emisor confiable. Medir costo y frescura con dos datasets sintéticos y repetir bajo carga combinada. Al superar el presupuesto, introducir proyecciones incrementales en PostgreSQL con watermark y reconstrucción idempotente. Aplicar umbrales del ADR antes de separar un servicio. [Decisión y protocolo](02-architecture-adrs.md)
2. En flujos que requieran replay, escribir evento y transacción de negocio juntos. El proyector deduplica por `event_id` y por identidad de negocio cuando distintos eventos convergen. Publicar métricas de espera y reconciliar el resumen con las fuentes transaccionales antes de activar cada KPI.
3. Conservar `/api/v1/analytics/summary` para consumidores existentes. Exponer métricas con definición y filtros explícitos mediante contrato nuevo versionado. Incluir `as_of`, `observed_through`, zona, alcance y cobertura, con acceso por tenant y permiso de negocio. El dashboard operativo usa telemetría agregada con permisos distintos. Los eventos de demo se consumen en su propio entorno y no se mezclan con producción.
4. Separar retención de eventos, auditoría y agregados. Definir plazos por finalidad con FK-27, reducir referencias personales y respetar solicitudes de borrado sin conservar copias de PII en proyecciones. Observar volumen, lag y errores con IDs de correlación y etiquetas de cardinalidad acotada.

Aceptación propuesta para FK-09, FK-10 y FK-26. Usar un dataset de dos empresas y probar denominador cero, cambio de día y hora local, duplicación, retraso, reconstrucción desde eventos, reapertura, importes en varias monedas y coste ausente. Comprobar que UI, API y consulta de reconciliación presentan los mismos totales para el mismo corte. Medir latencia y frescura con el protocolo del ADR y registrar resultado antes de prometer cobertura o rendimiento.
