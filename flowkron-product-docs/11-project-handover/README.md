# Handover técnico para desarrolladores

Versión: 2.0
Fecha de corte: 2026-07-23

Esta carpeta contiene lo necesario para que un equipo de desarrollo reciba, ejecute, mantenga y continúe Flowkron sin depender del equipo anterior.

## Orden de lectura

1. [Overview para desarrolladores](01-developer-overview.md)
2. [Arquitectura y flujos end-to-end](02-technical-architecture-and-flows.md)
3. [Datos, contratos y seguridad](03-data-contracts-and-security.md)
4. [Operación, despliegue y calidad](04-operations-deployment-and-quality.md)
5. [Deuda técnica y continuidad](05-known-gaps-and-continuity.md)
6. [Glosario](06-glossary.md)
7. [Inventario documental](07-documentation-inventory.md)

## Qué resuelve

- mapa de repositorios y ownership;
- topología y fronteras de confianza;
- flujos de login, tenant, provisioning, contexto y WhatsApp;
- modelo de datos y aislamiento;
- contratos y autenticación;
- configuración local y despliegue;
- cobertura de tests real;
- riesgos, stubs, modos legacy y deuda técnica;
- orden recomendado de continuidad.

## Fuentes canónicas

- [Estado de implementación](../04-architecture/00-current-implementation-status.md)
- [Catálogo de servicios](../04-architecture/12-service-catalog.md)
- [Catálogo de contratos](../04-architecture/13-contract-catalog.md)
- [Auth](../../flowkron-auth-service/docs/README.md)
- [Operational](../../flowkron-operational-service/docs/README.md)
- [Agent Core](../../flowkron-agent-core/docs/README.md)
- [App](../../flowkron-front-app-angular/docs/README.md)
- [Landing](../../flowkron-front-landing-angular/docs/README.md)
- [Deploy](../../flowkron-deploy/docs/README.md)
- [API Contracts](../../flowkron-api-contracts/README.md)

## Regla de evidencia

No asuma que algo existe por estar nombrado en un componente. Confirme ruta, implementación, configuración, contrato y prueba. Los estados permitidos están definidos en [README principal](../README.md).

