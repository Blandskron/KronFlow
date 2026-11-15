# Arquitectura del sistema

Versión: 1.3
Tipo: estado actual + arquitectura objetivo
Estado: `PARTIAL`
Última verificación técnica: 2026-07-23

## Estado actual

La arquitectura ejecutable se compone de dos frontends Angular, tres backends, PostgreSQL, Redis y el gateway de correo transaccional.

```text
Landing -> Auth para contacto público
App -> Auth + Operational + Agent Core
Auth -> Operational para runtime tenant
Agent Core -> Operational para persistencia y retrieval
Auth -> PostgreSQL + Redis
Operational -> PostgreSQL public + schema tenant
Auth -> smtp-http-blandskron -> Resend
```

El [paquete de handover](../11-project-handover/02-technical-architecture-and-flows.md) describe los flujos completos.

## Componentes

| Componente | Función | Estado |
| --- | --- | --- |
| Auth | IAM, tenants, RBAC, sesiones, JWT, MFA y auditoría | `IMPLEMENTED` con brechas |
| Operational | Runtime/schema tenant, CRM operacional, analytics e ingest | `PARTIAL` |
| Agent Core | Contexto, documentos, retrieval y conversación IA | `PARTIAL` |
| App | Experiencia privada | `PARTIAL` |
| Landing | Marketing y contacto | `PARTIAL` |
| SMTP HTTP Blandskron | Gateway transaccional | `IMPLEMENTED`, requiere credenciales de Resend |
| API Contracts | Interfaces compartidas | `PARTIAL` |
| Compose | Integración local | `IMPLEMENTED` local |

## Límites

- El adaptador de WhatsApp se opera por separado.
- El workflow exportado no consume todavía la ingest API de Operational.
- No hay plataforma productiva, TLS global, HA, observabilidad ni backups.
- No existe proveedor de pagos integrado.
- Operational no aplica RBAC granular por endpoint.

## Arquitectura objetivo

Son `PROPOSED`: gateway de canales por contrato, autorización operacional completa, migraciones tenant versionadas, colas/workers, vector store, abstracción LLM, billing, ingress/TLS, CI/CD, observabilidad y disaster recovery.

Cada incorporación requiere ADR, owner, contrato, threat model, pruebas, plan de migración y actualización del [estado actual](00-current-implementation-status.md).
