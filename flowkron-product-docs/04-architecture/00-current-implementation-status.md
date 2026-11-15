# Estado actual de implementación

Versión: 1.3
Tipo: Current State
Estado: `IMPLEMENTED` como inventario documental
Última verificación técnica: 2026-07-23

Esta es la vista transversal del sistema ejecutable. El código, la configuración y los contratos adoptados de cada repositorio propietario prevalecen sobre este documento. Consulte el [catálogo de servicios](12-service-catalog.md) y el [catálogo de contratos](13-contract-catalog.md) para el detalle verificable.

## Capacidades

| Capacidad | Estado | Propietario | Evidencia observada | Brecha principal |
| --- | --- | --- | --- | --- |
| Identidad, JWT, tenants y RBAC | `IMPLEMENTED` | Auth | Apps Django, rutas DRF, modelos y OpenAPI | Operational no aplica aún permisos RBAC granulares por router |
| Registro, correo, recuperación y MFA | `PARTIAL` | Auth + App | Endpoints/modelos Auth; UI privada | Gestión MFA y cobertura E2E de UI incompletas |
| Suscripción y provisioning operacional | `PARTIAL` | Auth + Operational | Runtime interno, schemas por tenant y activación síncrona | Sin checkout/webhooks de pago; migración tenant sin versionado completo |
| Dashboard de leads, conversaciones y analytics | `PARTIAL` | Operational + App | Rutas FastAPI y pantallas de lectura | Sin envío de mensajes; analytics calculado sin histórico consolidado |
| Agentes de Operational | `STUB` | Operational | Rutas `/api/v1/agents`; configuración no persistida | Debe converger con Agent Core o implementarse |
| Contexto empresarial y simulación IA | `PARTIAL` | Agent Core + Operational + App | Plantillas, carga documental, retrieval y simulación | Persistencia integrada parcial; no hay evaluación/costos ni vector store productivo |
| Landing y contacto público | `PARTIAL` | Landing + Auth | CSRF y `POST /contact/messages/` | Textos legales y pruebas browser-integradas pendientes |
| Adaptador WhatsApp | `PARTIAL` | Baileys (laboratorio) | Vínculo QR e ingesta opcional de texto con consentimiento registrado | Onboarding, respuestas del agente y campañas quedan pendientes |
| Ingesta HTTP tenant-aware | `IMPLEMENTED` | Operational | Rutas `/api/v1/ingest/whatsapp/*` y OpenAPI | Requiere credenciales y runtime habilitado |
| Contratos compartidos | `PARTIAL` | API Contracts | OpenAPI Auth v0.5.0, Operational y Agent Core v0.3.1; schemas y errores | Gateway WhatsApp sin paths formales y adopción endpoint a endpoint pendiente |
| Compose local | `IMPLEMENTED` | Deploy | Modelos Compose de infraestructura, backend, frontend y correo | Entorno local |
| CI/CD, monitorización, backups y DR probado | `NOT_IMPLEMENTED` | Plataforma | No hay workflows ni stack operativo versionados | Diseño, responsables y validación operativa pendientes |

## Estado de pruebas y validación

| Repositorio | Evidencia disponible | Límite que no debe ocultarse |
| --- | --- | --- |
| Auth | Tests Django documentados y checks locales | No equivalen a E2E ni cubren todos los flujos tenant |
| API Contracts | Validadores locales de JSON Schema, YAML y docs agent-first | No hay validación semántica OpenAPI completa integrada |
| Operational | Compilación y validaciones manuales documentadas | No existe suite automatizada ni pytest instalado |
| Agent Core | Suite pytest bajo `app/tests` | No prueba proveedor real ni integración productiva completa |
| Frontends | Build y smoke visual externo documentados | No hay target Angular unitario; screenshots no son regresión automática |
| Gateway de correo | pytest | Proveedor de correo simulado |
| Deploy | Validación estática Compose | Healthchecks son superficiales y no garantizan negocio |

## Regla de lectura

`IMPLEMENTED` prueba que hay evidencia en código/configuración. `PARTIAL` significa que hay una capacidad con límites explícitos. `STUB`, `PROPOSED` y `NOT_IMPLEMENTED` no deben venderse ni tratarse como disponibilidad operativa.
