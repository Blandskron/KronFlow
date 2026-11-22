# Auditoría del estado real de Flowkron Community v1

**Corte:** 22 de noviembre de 2026 · `main` · `3e53868699c3df939b17ed395fe49eb2daf1fab6`. El árbol incluía la corrección local del fixture de consentimiento y su registro de pruebas. [Roadmap canónico](../../../EVOLUCION_FLOWKRON.md) · [Preparación de release](../../../RELEASE_READINESS.md).

`IMPLEMENTED` indica una ruta activa que cubre el alcance descrito. `PARTIAL` indica cobertura funcional incompleta. `PLANNED` identifica una capacidad del roadmap sin recorrido activo identificado. `BROKEN` indica un fallo reproducido. `UNKNOWN` indica evidencia insuficiente. La evidencia observada proviene de código, pruebas existentes o CI. La evidencia validada indica una ejecución identificada. Las acciones son propuestas.

## Capacidades y brechas

| Superficie | Estado y evidencia | Severidad, riesgo y acción propuesta |
| --- | --- | --- |
| IAM, altas y equipos | **IMPLEMENTED.** `SignupView` y `TenantViewSet` cubren alta, onboarding, invitaciones y ciclo de vida. `HasTenantPermission` comprueba membresía y permisos. Las pruebas de límites abarcan roles, último propietario y acceso cruzado. [Cuentas](../../../flowkron-auth-service/apps/accounts/public_auth.py) · [Tenants](../../../flowkron-auth-service/apps/tenants/views.py) · [RBAC](../../../flowkron-auth-service/apps/rbac/test_boundaries.py) | **Media.** Confirmar recorrido de revocación por consumidor de JWT en la versión candidata. |
| JWT y revocación | **PARTIAL.** `TaggedTokenRefreshView` verifica sesión y membresía y vuelve a emitir claims. IAM incluye rotación e introspección. Los consumidores Operational y Agent verifican JWT localmente. [Refresh](../../../flowkron-auth-service/apps/accounts/views.py) · [Servicios de seguridad](../../../flowkron-auth-service/apps/security/services.py) · [Validador Operational](../../../flowkron-operational-service/app/core/security.py) · [Validador Agent](../../../flowkron-agent-core/app/core/security.py) | **Alta** para acciones irreversibles. Claims de acceso emitidos pueden sobrevivir al cambio de rol hasta caducar. Exigir autorización actual para nuevas operaciones sensibles. |
| Runtime y permisos Operational | **IMPLEMENTED.** `tenant_with_permission` usa el tenant autenticado y comprueba runtime activo. Lecturas CRM requieren `users.read`, edición `crm.manage`, agentes `agents.create` y vistas sensibles `audit.read`. La suite cubre permisos de escritura, payload sobredimensionado y separación de tenants. [Resolver](../../../flowkron-operational-service/app/core/tenant_resolver.py) · [Queries tenantizadas](../../../flowkron-operational-service/app/services/tenant_data.py) · [Pruebas](../../../flowkron-operational-service/tests/test_security.py) | **Media.** La documentación local de agentes describe un estado anterior de RBAC y filtros de plan. Reconciliarla con el runtime mediante FK-16. |
| Esquema y upgrades | **IMPLEMENTED** para el esquema activo. `ACTIVE_TENANT_TABLE_NAMES` define el provisioning. `apply_tenant_schema` aplica cambios repetibles y registra los upgrades; el valor actual es **v8**, posterior a v7 de recibos. V3 incorpora identidad, v4 turnos, v5 trabajos, v6 lectura y v8 orden de consentimiento. [Modelos activos](../../../flowkron-operational-service/app/tenant_models/__init__.py) · [Provisioning](../../../flowkron-operational-service/app/services/tenant_provisioning_service.py) · [Runbook](../../../flowkron-operational-service/docs/TURN_RECOVERY.md) | **Alta.** Un runtime existente puede requerir migración previa al conector nuevo. Ensayar backup, restauración y upgrade por versión con base descartable antes del release. |
| Contactos, leads y ventas | **PARTIAL.** `Cliente` y `Lead` se usan en la ingesta, la lectura y el PATCH de leads. La landing persiste su mensaje en IAM. No se identificó un recorrido activo de formulario genérico hacia CRM, un directorio multicanal ni entidad de oportunidad independiente. [Modelos](../../../flowkron-operational-service/app/tenant_models/operations.py) · [Ingesta](../../../flowkron-operational-service/app/services/ingest_service.py) · [Leads](../../../flowkron-operational-service/app/api/v1/leads.py) · [Formulario](../../../flowkron-auth-service/apps/contact/views.py) | **Alta** para producto v1. Definir identidad única, captación por ámbito y pipeline con fuente de verdad en Operational. [Especificación 03](03-inbound-crm.md) |
| WhatsApp, consentimiento y recibos | **PARTIAL.** El conector maneja QR, reconexión y cola local. Operational persiste turnos, reintentos, evidencia de envío y orden de ACEPTO/BAJA. Las suites sintéticas ejercitan recuperación, recibos fuera de orden y resultados inciertos. [Conexión](../../../flowkron-baileys-services/src/connection.ts) · [Turnos](../../../flowkron-operational-service/app/services/whatsapp_turn_service.py) · [Pruebas de cola](../../../flowkron-operational-service/tests/test_turn_jobs.py) | **Alta.** La persistencia comienza cuando Operational admite el turno. Sigue pendiente validar enlace, reinicio, entrega y baja en una cuenta autorizada y evaluar condiciones de distribución. |
| Inbox y atención humana | **PARTIAL.** Hay búsqueda SQL, cursor, historial y lectura compartida. El handoff se registra desde la ingesta. El router CRM de conversaciones expone lectura, sin operación activa para reclamar, responder o devolver control. [Inbox API](../../../flowkron-operational-service/app/api/v1/conversations.py) · [Handoff](../../../flowkron-operational-service/app/api/ingest/whatsapp.py) · [Pruebas de inbox](../../../flowkron-operational-service/tests/test_conversation_inbox.py) | **Alta.** Escalar sin control humano efectivo crea una brecha en el recorrido de atención. Priorizar FK-06 y FK-19. |
| Agent Core | **PARTIAL.** Existe procesamiento stateless para WhatsApp con contexto de Operational, rutas stateful condicionadas a persistencia y simulación. Hay acciones preparadas por herramientas simuladas, rutas de trazas protegidas y pruebas de límites de documentos. Configurar un perfil Operational devuelve 501. [Rutas](../../../flowkron-agent-core/app/api/v1/routes/agent.py) · [Orquestación](../../../flowkron-agent-core/app/application/orchestration/agent_runtime.py) · [Límites](../../../flowkron-agent-core/app/tests/test_security_boundaries.py) · [Perfil Operational](../../../flowkron-operational-service/app/services/agent_service.py) | **Alta.** Separar contexto no confiable de instrucciones y limitar las herramientas a propuestas. Validar aprobación, permisos y aislamiento antes de acciones reales. |
| Email y campañas | **PARTIAL** para transporte, **PLANNED** para campañas. `EmailService.send` autentica el cliente a través del endpoint, aplica reglas de remitente e idempotencia y devuelve aceptación. Existe entrada para webhook Resend. No se identificaron campaña, snapshot ni proyección de eventos de entrega en el CRM. [Gateway](../../../smtp-http-blandskron/app/main.py) · [Servicio](../../../smtp-http-blandskron/app/service.py) · [Pruebas de webhook](../../../smtp-http-blandskron/tests/test_webhooks.py) | **Alta.** Operar campañas requiere consentimiento específico, bajas y evidencia de entrega. [Especificación 04](04-campaigns.md) |
| Analítica y eventos | **PARTIAL.** `analytics_summary` agrega `Lead` y `Message`. `open_conversations` cuenta leads por estado. Hay esquemas de eventos y trabajos, y metadata de tenant en el envelope. No se identificó una proyección general de eventos de negocio. [Agregación](../../../flowkron-operational-service/app/services/analytics_service.py) · [Pruebas de metadata](../../../flowkron-operational-service/tests/test_contract_metadata.py) · [Contratos](../../../flowkron-api-contracts/schemas) | **Media.** Corregir semántica y derivar indicadores de evidencia por dominio antes de anunciar métricas de resultado. |
| Privacidad, backup y restauración | **PARTIAL / UNKNOWN.** Hay registro y lectura de solicitudes y suspensión de runtime. El restore operativo y la eliminación verificable entre bases, documentos y sesiones requieren evidencia de extremo a extremo. [Ingesta de solicitudes](../../../flowkron-operational-service/app/api/ingest/whatsapp.py) · [Gates actuales](../../../RELEASE_READINESS.md) | **Alta.** Asignar dueño de solicitudes, acotar retención y ensayar restauración con FK-27 y FK-15. |
| Compose, contratos y distribución | **IMPLEMENTED** para inicio local documentado y validado por los smoke del SHA base. **UNKNOWN** para instalación productiva y redistribución de imágenes. [Compose estándar](../../../compose.yaml) · [Demo](../../../compose.demo.yaml) · [Contratos](../../../flowkron-api-contracts/CONTRACT.md) · [Terceros](../../../THIRD_PARTY.md) | **Alta** si se anuncia como estable. Source preview Apache-2.0 es el alcance documentado. Completar inventario y notices del artefacto antes de publicar imágenes. |

## Rutas Angular activas

`authGuard` cubre el árbol `/app`. La columna de acceso se refiere también al control de la API; el guard de Angular por sí solo no autoriza recursos. Los aliases `integrations` y `pricing` redirigen. [Mapa CRM](../../../flowkron-front-app-angular/src/app/app.routes.ts) · [Mapa landing](../../../flowkron-front-landing-angular/src/app/app.routes.ts).

| Ruta y componente | Interacción, acceso y resultado | Evidencia o brecha |
| --- | --- | --- |
| `/login`, `/registrarse` · `LoginComponent`, `SignupPageComponent` | Pública, `noAuthGuard`. IAM `/auth/` para opciones, acceso y alta. | Smoke Compose y caso visual de login. |
| `/forgot-password`, `/confirm-email`, `/reset-password` · páginas IAM | Públicas. IAM `/auth/password/*` y `/auth/email/confirm/` devuelven estado transaccional. | Pruebas IAM existentes. UI completa del recorrido no reejecutada localmente. |
| `/onboarding/company` · `CreateCompanyPageComponent` | Sesión. IAM `POST /tenants/onboarding/` crea empresa y actualiza el acceso. | Smoke estándar y `test_verified_user_without_tenant_can_complete_onboarding`. |
| `/app/home`, `/app/analytics` · `HomePageComponent`, `AnalyticsPageComponent` | Lectura Operational `/analytics/summary` con `users.read`. Devuelve agregados tenantizados. | El nombre `open_conversations` requiere reconciliación con el cálculo actual. |
| `/app/business-context` · `BusinessContextPageComponent` | Documentos y simulación de Agent Core. Permisos y acciones disponibles según modo de persistencia. | Smoke demo de carga y simulación. Los endpoints stub de perfiles de Operational no prueban configuración persistente. |
| `/app/conversations` · `ChatsPageComponent` | `/conversations` e historial con `users.read`; lectura compartida con `crm.manage`. | Playwright usa API simulada. Suite ASGI/PG verifica cursor y permisos. |
| `/app/workflows` · `WorkflowsPageComponent` | Lee conversaciones y las clasifica para mostrar seguimiento. | Vista derivada de conversaciones. El guardado de etapa comercial no forma parte del flujo activo. |
| `/app/notifications` · `NotificationsPageComponent` | Lee `/conversations` filtrado por `requires_human`. | Lista de handoffs sin bandeja persistente de entregas. |
| `/app/whatsapp` · `WhatsAppPageComponent` | IAM autoriza y proxifica diagnósticos y QR de la empresa. | Pruebas de IAM y visual con API simulada. Enlace real pendiente. |
| `/app/settings` · `SettingsPageComponent` | Perfil IAM, gestión de miembros e invitaciones según permisos del tenant. | Pruebas IAM de límites. El smoke no cubre cada interacción. |
| Landing `/`, `/politica-privacidad` · página de producto y política | Navegación pública, formulario de contacto protegido por CSRF en IAM y enlaces a acceso/alta. | Smoke del formulario y caso visual de enlaces. El contacto de landing no crea un lead de empresa. |

[Pruebas visuales CRM](../../../flowkron-front-app-angular/tests/visual/flowkron-front.visual.spec.ts) · [Pruebas IAM](../../../flowkron-auth-service/apps/tenants/tests.py) · [Smoke Compose](../../../flowkron-deploy/bootstrap/smoke.py).

## Reconciliación de los 27 tickets

IDs y prioridades vigentes en [EVOLUCION_FLOWKRON.md](../../../EVOLUCION_FLOWKRON.md). Esta tabla describe evidencia al corte.

| ID | Estado al corte | Evidencia o brecha pendiente |
| --- | --- | --- |
| FK-01 | IMPLEMENTED | Identidades únicas y actualización de schemas, cubiertas por `test_message_identity.py`. |
| FK-02 | IMPLEMENTED | Reclamación, recuperación y reconciliación en `test_turn_recovery.py`. |
| FK-03 | PARTIAL | `WhatsAppTurnJob` persiste turnos. Extensión de cola a otros dominios pendiente. |
| FK-04 | PARTIAL | BAJA cancela trabajo elegible y v8 conserva el orden. Consentimiento por canal y finalidad y gate del worker de campañas pendientes. |
| FK-05 | IMPLEMENTED | Diagnóstico tenant de IAM, conector y UI. Cuenta real sin validar. |
| FK-06 | PARTIAL | Handoff y lista operativos. Reclamar, responder y devolver control pendientes. |
| FK-07 | IMPLEMENTED | Evidencia de envíos directos durables y recibos sintéticos normalizados. |
| FK-08 | IMPLEMENTED | Búsqueda, cursor y lectura cubiertos por `test_conversation_inbox.py`. |
| FK-09 | PARTIAL | `test_contract_metadata.py` verifica tenant resuelto. Faltan métricas end-to-end. |
| FK-10 | PARTIAL | Esquema de evento existente; publicación y suscripción tenant pendientes. |
| FK-11 | PLANNED | El webhook de entrada de Resend cubre otro propósito. Falta entrega saliente confiable de eventos de dominio. |
| FK-12 | PARTIAL | IAM ya administra API keys y cuentas de servicio. Falta consumo acotado por Operational para automatizaciones. |
| FK-13 | PLANNED | Carga de contexto existente. Adjuntos privados de conversación pendientes. |
| FK-14 | PARTIAL | Contratos incluyen identidad y conexión de WhatsApp. Falta soporte operativo de varias conexiones/proveedores. |
| FK-15 | PARTIAL | Smoke estándar/demo y recuperación sintética existentes. Restores, upgrade operativo y PG en CI pendientes. |
| FK-16 | PARTIAL | Runbooks recientes de turnos. Hay diferencias en instrucciones locales y readiness respecto al código activo. |
| FK-17 | PARTIAL | Agent Core prepara acciones simuladas. Falta persistencia y ejecución autorizada en Operational. |
| FK-18 | PLANNED | Falta bandeja de revisión de acciones tipadas y decisión auditable. |
| FK-19 | PARTIAL | Hay controles de acceso, suspensión y consentimiento. Falta control de IA por empresa/conversación con efecto en workers. |
| FK-20 | PARTIAL | Persistencia condicionada de Agent Core y contexto remoto. Falta memoria operativa acotada con retención definida. |
| FK-21 | PARTIAL | Operational admite campos de lead y contacto. Falta aplicar desde IA solo hechos confirmados y trazables. |
| FK-22 | PLANNED | Agenda con disponibilidad y confirmación pendiente. |
| FK-23 | PLANNED | Gateway de correo disponible. Falta envío comercial vinculado a conversación. |
| FK-24 | PARTIAL | IAM dispone de credenciales y el gateway autoriza remitentes. Falta delegación por empresa para conectores de negocio. |
| FK-25 | PARTIAL | La vista de notificaciones consulta handoffs. Falta centro con historial y evidencias de entrega. |
| FK-26 | PARTIAL | Hay trazas y pruebas del agente. Falta evaluación de negocio, presupuesto y controles comunes. |
| FK-27 | PARTIAL | La ingesta registra solicitudes de privacidad. Falta resolución y verificación de retención sobre las fuentes activas. |

## CI, pruebas y orden de cierre

- **Observado.** Validate sobre `3e538686` terminó con diez jobs exitosos y Operational fallido. Este job reportó 58 casos, un error y 45 omitidos. `save_consent` usa `cliente.id` al cargar `WhatsAppConsentState`; el `SimpleNamespace` del test no representaba un contacto persistido. El test necesitaba también la identidad tenant y los demás campos requeridos por auditoría. [Validate](https://github.com/Blandskron/flowkron/actions/runs/44824257725) · [Workflow](../../../.github/workflows/validate.yml)
- **Validado en Windows.** El fixture corregido pasa con la suite de Operational en PostgreSQL 18.3 descartable y `httpx2` temporal para el Starlette local. **57 aprobadas y una omitida** (benchmark optativo). El conector aprobó **32 pruebas sintéticas**. [Reproducción Operational](../../../flowkron-operational-service/docs/TESTING.md) · [Pruebas del conector](../../../flowkron-baileys-services/test/connector.test.mjs)
- **Prioridad 1 (FK-15).** Habilitar `FLOWKRON_TEST_POSTGRES_BIN` en el runner y comprobar los motivos de omisión en CI. De los 45 skips del baseline, 44 corresponden a la habilitación de PostgreSQL y uno es el benchmark optativo. Reproducir además desde las dependencias declaradas en CI.
- **Prioridad 2 (FK-06/12/19/21).** Cerrar control humano, captación acotada e identidad antes de campañas. Validar dos empresas y autorización por cada acción.
- **Prioridad 3 (FK-03/04/10/14/23/24).** Implementar el recorrido outbound de forma acotada detrás del gate por canal. Separar aceptación del proveedor de entrega confirmada.
- **Prioridad 4 (FK-09/15/16/26/27).** Alinear métricas, reconciliar docs y ejercer backup/restore, revocación efectiva y tratamiento de datos en configuración de release. Quedan sin validar localmente ambos smoke Compose, proveedores reales y redistribución.

```powershell
gh run list --branch main --limit 3 --json headSha,conclusion,url
gh run view 44824257725 --log-failed
Push-Location flowkron-operational-service
$env:FLOWKRON_TEST_POSTGRES_BIN = 'C:/Program Files/PostgreSQL/18/bin'
python -m unittest discover -s tests -v
Pop-Location
npm --prefix flowkron-baileys-services test
```
