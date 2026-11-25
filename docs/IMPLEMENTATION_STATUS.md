# Estado actual de implementación — KronFlow

**Versión:** `tenant_schema_v16`  
**Última verificación técnica:** 2026-11-25 (Reorganización `backend/` · `frontend/` · `deploy/`, Angular 21 Zoneless, WCAG 2.2 AA `31/31`, Lighthouse Desktop `100/100/100/100`)

Esta es la vista transversal del sistema ejecutable. El código, la configuración y la documentación propia de cada servicio prevalecen sobre este resumen.

## Capacidades

| Capacidad | Estado | Propietario | Evidencia observada | Brecha / Gate restante |
| --- | --- | --- | --- | --- |
| Identidad, JWT, tenants y RBAC | `IMPLEMENTED` | `backend/auth-service` + `backend/operational-service` | IAM emite JWT RS256 y Operational aplica permisos por ruta y selecciona el schema de la empresa | Operational valida access tokens localmente hasta su expiración |
| Registro, correo, recuperación y Google Sign-In | `IMPLEMENTED` | `backend/auth-service` + `frontend/app` | Signup por correo y Google Identity Services, recuperación de contraseña, perfil y avatar | Gestión avanzada de enrolamiento MFA UI pendiente |
| Suscripción y provisioning operacional | `IMPLEMENTED` | `backend/auth-service` + `backend/operational-service` | Runtime interno, schemas multiempresa y matriz repetible `v3–v16` | Ensayo de restore en entorno productivo (`FK-15`) |
| CRM, conversaciones, pipeline y métricas | `IMPLEMENTED` | `backend/operational-service` + `frontend/app` | Contactos, `contact_points`, formularios públicos, credenciales `leads:create`, control HITL CAS, compositor en vivo, oportunidades (`FK-29`), eventos de dominio (`FK-10`) y KPIs consolidados (`/api/v1/analytics/kpis`) | — |
| Campañas, conexiones delegadas y correo en hilo | `IMPLEMENTED` | `backend/operational-service` + `backend/mail-service` + `frontend/app` | Plantillas sanitizadas, snapshot deduplicado, worker stub integrado a outbox/consentimiento, bajas durables, recibos, conexiones delegadas (`FK-24`) y correo en hilo (`FK-23`) | Validación manual con sandbox Resend real; campañas WhatsApp deshabilitadas fuera de stub |
| Solicitudes de privacidad y retención | `IMPLEMENTED` | `backend/operational-service` + `frontend/app` | Bandeja restringida, exportación JSON (`/export`), anonimización/supresión durable (`/erase`) y barrido de retención (`/retention/sweep`) con `log_limpiezas` | Verificación de retención sobre backups externos |
| Extensiones IA, webhooks, adjuntos y agenda | `IMPLEMENTED` | `backend/operational-service` + `frontend/app` | Propuestas tipadas y revisión (`FK-17`/`18`), memoria acotada (`FK-20`), enriquecimiento confirmado (`FK-21`), notificaciones externas (`FK-25`), coste IA (`FK-26`), webhooks HMAC/SSRF (`FK-11`), adjuntos privados (`FK-13`) y agenda sin doble reserva (`FK-22`) | — |
| Contexto empresarial y simulación IA | `IMPLEMENTED` | `backend/agent-core` + `backend/operational-service` + `frontend/app` | Plantillas Word/PDF, carga documental, recuperación RAG con trazas, asistente setup y evaluación sintética ([EVALUATION.md](../backend/agent-core/docs/EVALUATION.md)) | Evaluación semántica con proveedor real en producción |
| Landing pública y contacto CSRF | `IMPLEMENTED` | `frontend/landing` + `backend/auth-service` | Floating Glassmorphism, `11/11` tests Vitest, WCAG 2.2 AA, Lighthouse Desktop `100/100/100/100`, CSRF + `POST /api/v1/contact/messages/` | Textos legales definitivos por operador de instancia |
| Adaptador WhatsApp | `PARTIAL` | `backend/baileys-services` (laboratorio) | QR, ingesta, turnos durables admitidos por Operational, consentimiento y recibos (`32/32` tests) | Validación manual en cuenta real autorizada (`FK-14`) |
| Contratos compartidos | `IMPLEMENTED` | Servicios + Arquitectura | OpenAPI por servicio (`/openapi.json`) y fronteras/reglas consolidadas en [`ARCHITECTURE.md`](../ARCHITECTURE.md) | Sincronización continua endpoint a endpoint |
| Compose local y CI | `IMPLEMENTED` | `deploy/` + `.github/workflows/validate.yml` | Validate verde (`45222208571`) + configs estándar/demo validadas con Compose y builds limpios | Revisión de excepción dev `picomatch` antes del 18 dic 2026 |

Ver también: [Arquitectura](../ARCHITECTURE.md) · [Readiness](../RELEASE_READINESS.md) · [Gates de release](planning/v1/RELEASE_GATES.md) · [Trazabilidad](planning/v1/TRACEABILITY.md) · [Rutas CRM](../frontend/app/docs/ROUTES_AND_APIS.md).
