# Estado actual de implementación — KronFlow

Versión: 1.6
Última verificación técnica: 2026-11-25 (Rebranding KronFlow + Angular 21 Zoneless + WCAG 2.2 AA)

Esta es la vista transversal del sistema ejecutable. El código, la configuración y la documentación propia de cada microservicio prevalecen sobre este resumen.

## Capacidades

| Capacidad | Estado | Propietario | Evidencia observada | Brecha / Gate restante |
| --- | --- | --- | --- | --- |
| Identidad, JWT, tenants y RBAC | `IMPLEMENTED` | Auth + Operational | IAM emite JWT RS256 y Operational aplica permisos por ruta y selecciona el schema de la empresa | Operational valida access tokens localmente hasta su expiración |
| Registro, correo, recuperación y MFA | `PARTIAL` | Auth + App | Endpoints/modelos Auth; UI privada | Gestión MFA y cobertura E2E de UI incompletas |
| Suscripción y provisioning operacional | `IMPLEMENTED` | Auth + Operational | Runtime interno, schemas multiempresa y matriz repetible `v3–v16` | Restore completo de instalación en entorno productivo |
| CRM, conversaciones, pipeline y métricas | `IMPLEMENTED` | Operational + App | Contactos, `contact_points` + backfill, formularios públicos, credenciales `leads:create`, control HITL CAS, bloqueo IA, oportunidades (`FK-29`), eventos de dominio (`FK-10`) y KPIs consolidados (`/api/v1/analytics/kpis`) | — |
| Campañas, conexiones delegadas y correo en hilo | `IMPLEMENTED` | Operational + Gateway + App | Plantillas sanitizadas, snapshot deduplicado, worker stub integrado a outbox/consentimiento, bajas durables, recibos, conexiones delegadas (`FK-24`) y correo en hilo (`FK-23`) | Validación manual con sandbox Resend real; campañas WhatsApp deshabilitadas fuera de stub |
| Solicitudes de privacidad y retención | `IMPLEMENTED` | Operational + App | Bandeja restringida, exportación JSON (`/export`), anonimización/supresión durable (`/erase`) y barrido de retención (`/retention/sweep`) con `log_limpiezas` | Verificación de retención sobre backups externos |
| Extensiones IA, webhooks, adjuntos y agenda | `IMPLEMENTED` | Operational + App | Propuestas tipadas y revisión (`FK-17`/`18`), memoria acotada (`FK-20`), enriquecimiento confirmado (`FK-21`), notificaciones externas (`FK-25`), coste IA (`FK-26`), webhooks HMAC/SSRF (`FK-11`), adjuntos privados (`FK-13`) y agenda sin doble reserva (`FK-22`) | — |
| Contexto empresarial y simulación IA | `IMPLEMENTED` | Agent Core + Operational + App | Plantillas, carga documental, recuperación, simulación y evaluación sintética con presupuesto por solicitud | Evaluación semántica con proveedor real en producción |
| Landing y contacto público | `PARTIAL` | Landing + Auth | CSRF, `POST /contact/messages/` y build limpio | Textos legales finales y pruebas browser-integradas |
| Adaptador WhatsApp | `PARTIAL` | Baileys (laboratorio) | QR, ingesta, turnos durables admitidos por Operational, consentimiento y recibos (32/32 tests) | Validación manual en cuenta real autorizada (`FK-14`) |
| Contratos compartidos | `IMPLEMENTED` | API Contracts | JSON Schema, YAML y docs validados en CI | Sincronización continua endpoint a endpoint |
| Compose local y CI | `IMPLEMENTED` | Deploy + CI | Validate verde (`45222208571`): builds, PostgreSQL, Compose estándar/demo y auditorías | Revisión de excepción `picomatch` antes del 18 dic 2026 |

Ver también: [Arquitectura](../ARCHITECTURE.md) · [Readiness](../RELEASE_READINESS.md) · [Gates de release](planning/v1/RELEASE_GATES.md) · [Trazabilidad](planning/v1/TRACEABILITY.md) · [Rutas CRM](../flowkron-front-app-angular/docs/ROUTES_AND_APIS.md).
