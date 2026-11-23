# Estado actual de implementación

Versión: 1.4
Tipo: Current State
Estado: `IMPLEMENTED` como inventario documental
Última verificación técnica: 2026-11-23

Esta es la vista transversal del sistema ejecutable. El código, la configuración y los contratos adoptados de cada repositorio propietario prevalecen sobre este documento. Consulte el [catálogo de servicios](12-service-catalog.md) y el [catálogo de contratos](13-contract-catalog.md) para el detalle verificable.

## Capacidades

| Capacidad | Estado | Propietario | Evidencia observada | Brecha principal |
| --- | --- | --- | --- | --- |
| Identidad, JWT, tenants y RBAC | `IMPLEMENTED` | Auth + Operational | IAM emite JWT y Operational aplica permisos por ruta y selecciona el schema de la empresa | Operational valida el token de acceso localmente hasta su expiración |
| Registro, correo, recuperación y MFA | `PARTIAL` | Auth + App | Endpoints/modelos Auth; UI privada | Gestión MFA y cobertura E2E de UI incompletas |
| Suscripción y provisioning operacional | `PARTIAL` | Auth + Operational | Runtime interno, schemas multiempresa y registro de migración tenant | Quedan checkout y verificación de recuperación sobre un candidato completo |
| CRM, conversaciones y métricas | `PARTIAL` | Operational + App | Contactos manuales, seguimiento de leads, Bandeja, historial de derivaciones y actividad diaria por zona | Quedan oportunidad independiente, control humano efectivo, captura pública y métricas por eventos |
| Solicitudes de privacidad | `PARTIAL` | Operational + App | Bandeja restringida y registro auditado de revisión y cierre | Quedan ejecución de solicitudes y verificación de retención en almacenes activos y copias |
| Agentes de Operational | `STUB` | Operational | Rutas `/api/v1/agents`; configuración no persistida | Debe converger con Agent Core o implementarse |
| Contexto empresarial y simulación IA | `PARTIAL` | Agent Core + Operational + App | Plantillas, carga documental, recuperación, simulación y evaluación sintética con presupuesto por solicitud | Quedan trazas integradas, evaluación semántica con proveedor autorizado y coste acumulado |
| Landing y contacto público | `PARTIAL` | Landing + Auth | CSRF y `POST /contact/messages/` | Textos legales y pruebas browser-integradas pendientes |
| Adaptador WhatsApp | `PARTIAL` | Baileys (laboratorio) | QR, ingesta, turnos durables admitidos por Operational, consentimiento y recibos | Quedan validación en cuenta autorizada y campañas vía proveedor habilitado |
| Ingesta HTTP tenant-aware | `IMPLEMENTED` | Operational | Rutas `/api/v1/ingest/whatsapp/*` y OpenAPI | Requiere credenciales y runtime habilitado |
| Contratos compartidos | `PARTIAL` | API Contracts | OpenAPI Auth v0.5.0, Operational y Agent Core v0.3.1; schemas y errores | Gateway WhatsApp sin paths formales y adopción endpoint a endpoint pendiente |
| Compose local | `IMPLEMENTED` | Deploy | Modelos Compose de infraestructura, backend, frontend y correo | Entorno local |
| CI, recuperación y operación | `PARTIAL` | Plataforma | Validate versionado, smoke de Compose y ensayos sintéticos de upgrade y restore cifrado de Operational | Quedan gates sobre el candidato, recuperación de toda la instalación, métricas operativas y RPO/RTO |

## Estado de pruebas y validación

| Repositorio | Evidencia disponible | Límite que no debe ocultarse |
| --- | --- | --- |
| Auth | Tests Django documentados y checks locales | No equivalen a E2E ni cubren todos los flujos tenant |
| API Contracts | Validadores locales de JSON Schema, YAML y docs agent-first | No hay validación semántica OpenAPI completa integrada |
| Operational | Unittest con PostgreSQL descartable, ASGI, restore y matriz de upgrade | Datos sintéticos. Queda la validación sobre el candidato |
| Agent Core | Suite pytest bajo `app/tests` | No prueba proveedor real ni integración productiva completa |
| Frontends | Build y smoke visual externo documentados | No hay target Angular unitario; screenshots no son regresión automática |
| Gateway de correo | pytest | Proveedor de correo simulado |
| Deploy | Validación Compose y smoke estándar/demo en CI | Queda la verificación del candidato y de proveedores habilitados |

El repositorio sigue en source preview. El [estado de release](../../RELEASE_READINESS.md), los [gates](../../docs/planning/v1/RELEASE_GATES.md) y el [inventario de rutas](../../flowkron-front-app-angular/docs/ROUTES_AND_APIS.md) detallan la separación entre evidencia local y aceptación del candidato.

## Regla de lectura

`IMPLEMENTED` prueba que hay evidencia en código/configuración. `PARTIAL` significa que hay una capacidad con límites explícitos. `STUB`, `PROPOSED` y `NOT_IMPLEMENTED` no deben venderse ni tratarse como disponibilidad operativa.
