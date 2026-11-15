# Catálogo de servicios verificado

Versión: 1.0
Tipo: inventario técnico actual
Estado: `IMPLEMENTED` como documentación de referencia
Última verificación: 2026-07-23

## Criterio de lectura

La tabla describe ownership y límites observados en código, OpenAPI, Compose. No es un catálogo comercial ni una promesa de disponibilidad. Las rutas y payloads completos pertenecen al OpenAPI y a la documentación del repositorio propietario.

| Componente | Rol y tecnología | Interfaces/consumidores | Estado y límites relevantes | Fuente canónica |
| --- | --- | --- | --- | --- |
| Auth Service | IAM con Django/DRF: usuarios, tenants, membresías, RBAC, sesiones, tokens, MFA y contacto | App privada, landing, Operational por contrato interno | `PARTIAL`: API keys se administran, pero no hay autenticación DRF `ApiKey`; health no comprueba dependencias | [docs Auth](../../flowkron-auth-service/docs/README.md) |
| Operational Service | FastAPI + SQLAlchemy; runtime y datos multi-schema por tenant | App, Auth interno, Agent Core interno; API de ingest preparada | `PARTIAL`: valida JWT/tenant/plan, pero no RBAC por endpoint; `/agents` es stub; no hay suite automática | [docs Operational](../../flowkron-operational-service/docs/README.md) |
| Agent Core | FastAPI conversacional, contexto empresarial, plantillas y retrieval | App privada; Operational interno | `PARTIAL`: modo integrado delega documentos/status/retrieval a Operational; formularios, reglas, historiales y trazas son locales o `501` | [docs Agent Core](../../flowkron-agent-core/docs/README.md) |
| Frontend privado | Angular 21, SPA autenticada | Auth, Operational y Agent Core | `PARTIAL`: conversaciones son solo lectura, workflows son una vista derivada, notificaciones/integraciones son placeholders; no hay tests unitarios Angular | [docs App](../../flowkron-front-app-angular/docs/README.md) |
| Landing | Angular 21 pública, estática con Nginx | Auth para CSRF y contacto; WhatsApp de ventas | `PARTIAL`: el contacto HTTP es real; el email hero no está conectado y los legales son provisionales | [docs Landing](../../flowkron-front-landing-angular/docs/README.md) |
| Gateway de correo | Correo transaccional HTTP | Redis, Resend | `smtp-http-blandskron` |
| API Contracts | OpenAPI 3.1, JSON Schema, errores, ejemplos y versionado | Todos los productores/consumidores de interfaces | `PARTIAL`: Auth, Operational y Agent Core tienen specs; WhatsApp Gateway no expone paths formales aún | [contracts](../../flowkron-api-contracts/README.md) |
| Docker Compose | Integración local de infra, backend y frontends | Desarrollo local | `IMPLEMENTED` local; incluye el gateway de correo | [docs Deploy](../../flowkron-deploy/docs/README.md) |

## Dependencias e identidad de confianza

```text
Landing ── CSRF/contacto ────────────────> Auth
App ── JWT + X-Tenant-ID ────────────────> Auth / Operational / Agent Core
Auth ── X-Internal-Token ────────────────> Operational
Agent Core ── X-Internal-Token ──────────> Operational
```

Los adaptadores WhatsApp externos deben consumir la API de ingesta con cabeceras `X-Tenant-Code` y `X-Ingest-Key`.

## Operación local

`flowkron-deploy/docker-compose.yml` incluye infraestructura, backend, frontend y gateway de correo.

## Auditorías por propietario
