# ADR-0001 - API Contracts Repository

Estado: Aceptado

## Contexto

Flowkron tiene multiples servicios y frontends. Sin contratos centrales, las respuestas, errores, eventos y metadata pueden divergir.

## Decision

Crear `flowkron-api-contracts` como repositorio central de contratos publicos, esquemas, OpenAPI, eventos, errores y documentacion agentica.

## Consecuencias

- Mejora consistencia entre servicios.
- Reduce acoplamiento interno.
- Agrega disciplina de versionado.
- Requiere mantener contratos sincronizados con implementaciones reales.
