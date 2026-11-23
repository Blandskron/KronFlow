# Roadmap de Flowkron Community v1.0

**Estado al 23 de noviembre de 2026:** implementación funcional completa de Community v1.0 y capacidades POST-v1 sobre **`tenant_schema_v16`** (aditivo y repetible desde `v3` hasta `v16`), licencia Apache-2.0.

- [Alcance v1.0](docs/planning/v1/FINAL_SCOPE.md) · [Arquitectura y ADR](docs/planning/v1/02-architecture-adrs.md) · [Trazabilidad código/pruebas](docs/planning/v1/TRACEABILITY.md) · [Gates de release](docs/planning/v1/RELEASE_GATES.md) · [Readiness](RELEASE_READINESS.md)

## Resumen de estado (28 de 30 tickets `DONE`)

- **Implementado y verificado en PostgreSQL 18 (28 tickets `DONE`):**
  - **F1 · Estabilización:** `FK-01`, `FK-02`, `FK-03`, `FK-04`, `FK-05`, `FK-07`, `FK-08`, `FK-16`
  - **F2 · CRM inbound, HITL y pipeline:** `FK-06`, `FK-10`, `FK-12`, `FK-17`, `FK-18`, `FK-19`, `FK-20`, `FK-21`, `FK-28`, `FK-29`
  - **F3 · Campañas e integraciones:** `FK-23`, `FK-24`, `FK-30`
  - **F4/F5 · Métricas, gobernanza y privacidad:** `FK-09`, `FK-25`, `FK-26`, `FK-27`
  - **Extensiones POST-v1:** `FK-11` (webhooks fiables), `FK-13` (adjuntos privados), `FK-22` (agenda conversacional)
- **Pendientes únicamente de validación externa / operativa (2 tickets `IN_PROGRESS`):**
  - **`FK-14` · Conexiones y proveedores:** validación manual con cuenta real autorizada de WhatsApp (laboratorio) y sandbox real de Resend cuando el operador habilite envío productivo.
  - **`FK-15` · Recuperación y CI:** verificación final del workflow [Validate](.github/workflows/validate.yml) y Compose sobre el SHA candidato de release, ensayo de restore de instalación completa (RPO/RTO) y revisión de la excepción `picomatch` antes del **18 de diciembre de 2026**.

## Backlog canónico

| ID | Estado | Fase · prioridad | Dueño | Evidencia principal |
| --- | --- | --- | --- | --- |
| FK-01 · Identidad de mensajes | DONE | F1 · P0 | Operational, Contratos | Identidad durable, dedup y upgrade repetible. |
| FK-02 · Turnos recuperables | DONE | F1 · P0 | Operational, Conector | Reclamación, reinicio y reconciliación sin reenvío ciego. |
| FK-03 · Trabajos durables | DONE | F1 · P0 | Operational, Conector | Cola WhatsApp y outbox durable (`action_outbox_jobs`) con idempotencia, lease, `unknown` y verificación de efectos. |
| FK-04 · Consentimiento al ejecutar | DONE | F1/F3 · P0 | Operational, Canales | Ledger persistente por canal/finalidad (`contact_consent_decisions`, `contact_suppressions`) y autorización transaccional del worker. |
| FK-05 · Diagnóstico de conexión | DONE | F1 · P1 | IAM, Conector, CRM | QR y diagnóstico aislados y probados con adaptador sintético. |
| FK-06 · Atención humana y envío | DONE | F2 · P0 | Operational, IAM, CRM | Control HITL con CAS (`conversation_controls`), respuesta humana idempotente en outbox (`202`), resolución y retorno a IA. |
| FK-07 · Recibos y estados | DONE | F1 · P0 | Operational, Conector | Recibos normalizados y estados inciertos reconciliables. |
| FK-08 · Inbox y búsqueda | DONE | F1 · P1 | Operational, CRM | Paginación, búsqueda SQL y marcas de lectura concurrentes. |
| FK-09 · Trazas y métricas | DONE | F4 · P1 | Operational, Agent, CRM | Metadata tenant, Bandeja, actividad diaria y KPIs consolidados (`/api/v1/analytics/kpis`). |
| FK-10 · Eventos de dominio | DONE | F2 · P1 | Operational, Contratos | Eventos versionados persistentes (`domain_events`), replay hacia delante y checkpoints monotónicos. |
| FK-11 · Entrega fiable de webhooks | DONE | POST-v1 · P2 | Operational, Deploy | Suscripciones HTTPS con guarda SSRF, firma HMAC-SHA256, dedup e intentos acotados (`dead_letter`). |
| FK-12 · Credenciales acotadas | DONE | F2 · P0 | IAM, Operational | Credenciales `leads:create` (`scoped_integration_credentials`) con emisión, expiración y revocación. |
| FK-13 · Adjuntos privados | DONE | POST-v1 · P2 | Operational, CRM | Adjuntos privados (`private_attachments`) con lista blanca MIME, límite 10 MB, acceso por recurso y retención TTL. |
| FK-14 · Conexiones y proveedores | IN_PROGRESS | F3 · P1 | Canales, IAM | Restan pruebas manuales con cuenta real autorizada de WhatsApp / sandbox externo. |
| FK-15 · Recuperación y CI | IN_PROGRESS | F1/F5 · P0 | Deploy, Operational, CI | Matriz `v3–v16` y restore cifrado de Operational probados; resta validar SHA candidato en CI y restore completo. |
| FK-16 · Documentación verificable | DONE | F1/F4 · P1 | Plataforma | Inventario, contratos y trazabilidad reconciliados contra el código vigente (`v16`). |
| FK-17 · Propuestas y ejecución | DONE | F2 · P0 | Agent, Operational | Propuestas tipadas (`ai_action_proposals`), validación de runtime y ejecución `at-most-once`. |
| FK-18 · Revisión de acciones | DONE | F2 · P1 | Operational, IAM, CRM | Aprobación, rechazo y expiración versionada (`proposal_version`) vía API REST. |
| FK-19 · Control efectivo de IA | DONE | F2 · P0 | Operational, Agent, IAM | Policy global (`tenant_ai_policies`) y control por conversación que bloquean nuevos permisos IA sin alterar envíos en curso. |
| FK-20 · Memoria acotada | DONE | F2 · P2 | Operational, Agent | Memoria operativa por conversación (`conversation_memory_items`) con origen, TTL y purga. |
| FK-21 · Datos confirmados | DONE | F2 · P2 | Operational, Agent, CRM | Candidatos de enriquecimiento (`contact_enrichment_candidates`) con control de conflicto (`409`). |
| FK-22 · Agenda conversacional | DONE | POST-v1 · P2 | Operational, Agent, CRM | Simulación y confirmación concurrente sin doble reserva (`calendar_appointments` con advisory lock). |
| FK-23 · Correo vinculado a conversación | DONE | SHOULD F3 · P2 | Operational, Gateway | Envío idempotente de correo vinculado al hilo (`POST /conversations/{id}/email`) bajo conexión verificada. |
| FK-24 · Integraciones delegadas | DONE | F3 · P1 | IAM, Operational | Conexiones delegadas por empresa (`tenant_channel_connections`) con rotación y revocación. |
| FK-25 · Notificaciones | DONE | SHOULD F4 · P2 | Operational, CRM | Cola vigente, historial de derivaciones y entregas externas deduplicadas con recibos. |
| FK-26 · Evaluación y presupuestos de IA | DONE | F4 · P1 | Agent, Operational | Dataset sintético, presupuesto por solicitud y ledger de uso/coste acumulado (`ai_usage_records`). |
| FK-27 · Privacidad y retención | DONE | F5 · P0 | Operational, IAM, Deploy | Bandeja auditada, exportación JSON (`/export`), anonimización/supresión (`/erase`) y barrido de retención (`/retention/sweep`). |
| FK-28 · Directorio y captación CRM | DONE | F2 · P0 | Operational, CRM, IAM | Directorio, `contact_points`, backfill repetible con cuarentena de colisiones, formularios públicos y captación idempotente. |
| FK-29 · Pipeline comercial | DONE | F2 · P1 | Operational, CRM | Oportunidades persistentes (`pipeline_stages`, `opportunities`, `opportunity_activities`) con versión optimista y cierre `won`/`lost`. |
| FK-30 · Campañas y plantillas | DONE | F3 · P0 | Operational, Canales | Plantillas sanitizadas, snapshot deduplicado, worker stub integrado a outbox/consentimiento, bajas y recibos. |
