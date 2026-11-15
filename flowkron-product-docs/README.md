# Flowkron — documentación técnica para desarrollo

Versión documental: 3.0
Fecha de corte técnico: 2026-07-23

Este repositorio contiene exclusivamente documentación técnica para desarrollar, mantener, operar y transferir Flowkron. El contenido de negocio, producto, research, Scrum, marketing, ventas, SLA y assets comerciales fue retirado.

Comience por el [handover para desarrolladores](11-project-handover/README.md).

## Estado del sistema

Flowkron integra IAM, Operational, Agent Core, dos aplicaciones Angular y un gateway de correo transaccional, con contratos compartidos y un entorno local Compose.

La base técnica funciona parcialmente. No debe considerarse productiva hasta cerrar autorización Operational, migraciones tenant, tests integrados, secretos, TLS, observabilidad, backups y CI/CD.

## Contenido

| Sección | Contenido |
| --- | --- |
| [04 — Arquitectura](04-architecture/) | Estado real, servicios, base de datos, multi-tenancy, IAM, APIs, integraciones y ADR |
| [05 — Ingeniería de IA](05-ai-engineering/) | Agent Core, RAG, memoria, prompts, tools, modelos, evaluación y costos |
| [06 — Seguridad técnica](06-security-compliance/) | Autenticación, RBAC, privacidad técnica, auditoría, backups y controles |
| [07 — DevOps y operaciones](07-devops-operations/) | Infraestructura, ambientes, Docker, CI/CD, logging, monitoring, DR y despliegue |
| [11 — Handover de desarrollo](11-project-handover/) | Guía de continuidad, flujos, contratos, riesgos y checklist de mantenimiento |

La numeración `04`–`07` se conserva para no romper enlaces históricos y referencias cruzadas.

## Lecturas esenciales

1. [Overview para desarrolladores](11-project-handover/01-developer-overview.md)
2. [Arquitectura y flujos end-to-end](11-project-handover/02-technical-architecture-and-flows.md)
3. [Datos, contratos y seguridad](11-project-handover/03-data-contracts-and-security.md)
4. [Operación, despliegue y calidad](11-project-handover/04-operations-deployment-and-quality.md)
5. [Deuda técnica y continuidad](11-project-handover/05-known-gaps-and-continuity.md)
6. [Inventario documental técnico](11-project-handover/07-documentation-inventory.md)
7. [Estado actual de implementación](04-architecture/00-current-implementation-status.md)

## Estados técnicos

| Estado | Significado |
| --- | --- |
| `IMPLEMENTED` | Existe evidencia en código o configuración |
| `PARTIAL` | Existe con cobertura o controles incompletos |
| `STUB` | La interfaz existe sin implementar la capacidad |
| `PROPOSED` | Diseño técnico pendiente |
| `NOT_IMPLEMENTED` | No existe en el runtime |
| `DEPRECATED` | No debe seguir usándose |

## Jerarquía de fuentes

1. Código y configuración ejecutable.
2. Contratos adoptados en [`flowkron-api-contracts`](../flowkron-api-contracts/README.md).
3. OpenAPI generado por el servicio.
4. Documentación canónica del repositorio propietario.
5. ADR aceptados.
6. Esta vista transversal.

## Repositorios propietarios

| Repositorio | Responsabilidad | Documentación |
| --- | --- | --- |
| `flowkron-auth-service` | IAM, tenants, RBAC, sesiones y JWT | [docs](../flowkron-auth-service/docs/README.md) |
| `flowkron-operational-service` | Runtime, schemas tenant y datos operacionales | [docs](../flowkron-operational-service/docs/README.md) |
| `flowkron-agent-core` | Runtime conversacional y contexto empresarial | [docs](../flowkron-agent-core/docs/README.md) |
| `flowkron-front-app-angular` | SPA privada | [docs](../flowkron-front-app-angular/docs/README.md) |
| `flowkron-front-landing-angular` | SPA pública y contacto | [docs](../flowkron-front-landing-angular/docs/README.md) |
| `smtp-http-blandskron` | Gateway de correo transaccional | [README](../smtp-http-blandskron/README.md) |
| `flowkron-api-contracts` | OpenAPI, JSON Schema y errores | [README](../flowkron-api-contracts/README.md) |
| `flowkron-deploy` | Integración local | [docs](../flowkron-deploy/docs/README.md) |

## Reglas de mantenimiento

- Actualice primero el repositorio propietario.
- Sincronice OpenAPI/JSON Schema y consumidores.
- Distinga estado actual de arquitectura objetivo.
- No documente stubs, mocks o UI como capacidad backend.
- No incluya `.env`, secretos, tokens, claves, PII ni rutas personales.
- Valide UTF-8, enlaces relativos, fences Markdown, y contratos.

