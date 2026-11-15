# ADR-010 - Repositorio central de contratos API
> Historical record. The former bundled channel workflow was removed in the Flowkron transition. For the current topology, see the repository architecture.

Estado: Propuesto (`PROPOSED`)

## Contexto

Flowkron ya tiene servicios Django, FastAPI, frontends Angular, flujo de canal anterior y despliegue local integrado. Sin una fuente contractual compartida, cada pieza puede definir formatos de respuesta, error, evento, paginaciÃ³n y metadata de forma distinta.

## DecisiÃ³n propuesta

Adoptar `flowkron-api-contracts` como repositorio central para contratos compartidos:

- JSON Schema.
- OpenAPI por servicio.
- Eventos y webhooks.
- Respuestas y errores estÃ¡ndar.
- Contratos IA/jobs/auditorÃ­a.
- Ejemplos y validaciones.
- DocumentaciÃ³n operativa AI-First.

## Estado actual

El repositorio existe y contiene una fundación inicial. La adopción runtime es `PARTIAL`: contacto público Landing -> Auth ya tiene contrato inicial; Auth y Operational responden `ApiResponse`/`ApiError` en runtime; Angular desempaca `data`; el adaptador de canal conserva pendiente el contrato formal completo de cada tool/endpoint ingest.

## Consecuencias

- Todo endpoint nuevo debe revisar primero `flowkron-api-contracts`.
- Las migraciones de response/error deben ser compatibles o versionadas.
- El adaptador de canal no debe consumir estructuras improvisadas cuando exista contrato.
- Los SDKs generados quedan pendientes hasta completar auditorÃ­a contractual.

## Pendiente

Completar la matriz de [AlineaciÃ³n con `flowkron-api-contracts`](../09-contract-alignment.md) endpoint por endpoint.
