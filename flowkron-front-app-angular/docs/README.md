# Documentación de flowkron-front-app-angular

Documentación contrastada con código y configuración actuales.

| Documento | Contenido |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitectura, estado y alcance funcional |
| [ROUTES_AND_APIS.md](ROUTES_AND_APIS.md) | Rutas, guards, APIs y contratos |
| [CONFIGURATION_AND_OPERATIONS.md](CONFIGURATION_AND_OPERATIONS.md) | Environment, build, Docker y operación |
| [TESTING.md](TESTING.md) | Cobertura real y estrategia pendiente |

Las instrucciones agenticas se mantienen solo en [../AGENTS.md](../AGENTS.md). No se conserva una copia paralela bajo `docs/agent/`.

## Mantenimiento

- Rutas/guards/endpoints/DTOs: actualizar `ROUTES_AND_APIS.md`.
- Funcionalidad o estado de pantallas: actualizar `ARCHITECTURE.md`.
- Environment/Docker/Nginx: actualizar `CONFIGURATION_AND_OPERATIONS.md`.
- No llamar unit test a una suite inexistente ni regresión visual a screenshots sin baseline.
