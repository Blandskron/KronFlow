# Contrato Arquitectonico

`flowkron-api-contracts` es la fuente central de contratos externos y operativos de la plataforma Flowkron.

## Problema


## Decision

Mantener en este repositorio contratos reutilizables y documentacion operativa:

- JSON Schema para respuestas, errores, jobs, IA, eventos, webhooks y auditoria.
- OpenAPI por servicio.
- Catalogos de error por dominio.
- Ejemplos validos.
- Reglas de versionado y analisis de breaking changes.
- Documentacion para agentes IA.

## Limites

Este repositorio no debe contener:

- Modelos internos de Django o SQLAlchemy.
- Queries SQL, repositorios, servicios de dominio o casos de uso.
- Routers productivos, workers o adapters.
- Conexiones a bases de datos.
- Secretos o variables reales.
- Logica que obligue a un microservicio a depender internamente de otro.

## Servicios impactados

- `flowkron-auth-service`: respuestas, errores, eventos tenant/user y OpenAPI.
- `flowkron-operational-service`: IA, jobs, eventos, analytics y contratos multi-tenant.
- `flowkron-agent-core`: contrato omnicanal de runtime conversacional, RAG, fuentes, acciones preparadas y handoff humano. No define ni resuelve schemas fisicos.
- `flowkron-front-app-angular`: SDK/tipos futuros, errores globales y paginacion.
- `flowkron-front-landing-angular`: contacto publico y respuestas de formulario.
- `flowkron-deploy`: validacion y despliegue, sin logica de contratos.

## Base contractual de validacion

La base incluye `ApiResponse`, `ApiError`, `PaginatedResponse`, `AsyncJob`, `DomainEvent`, contratos AI, OpenAPI por servicio y ejemplos validos.
