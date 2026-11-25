# Documentación de KronFlow CRM (`frontend/app`)

Documentación alineada con el código y la configuración vigentes (`Angular 21.2 Zoneless`, `OnPush`, `Vitest`, `ESLint`).

| Documento | Contenido |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitectura Feature-Based/DDD, estado con Signals y límites del cliente |
| [ROUTES_AND_APIS.md](ROUTES_AND_APIS.md) | Rutas, guards y endpoints consumidos en IAM, Operational y Agent Core |
| [CONFIGURATION_AND_OPERATIONS.md](CONFIGURATION_AND_OPERATIONS.md) | Environments, build args, Docker y Nginx |
| [SECURITY.md](SECURITY.md) | Tokens RS256, XSS, CORS y manejo seguro de almacenamiento local |
| [TESTING.md](TESTING.md) | Suite Vitest (`28/28`), ESLint a11y, Playwright y auditoría WCAG 2.2 AA |

Las instrucciones agénticas se consolidan únicamente en [../AGENTS.md](../AGENTS.md).

## Mantenimiento

- Rutas, guards, endpoints o DTOs: actualizar `ROUTES_AND_APIS.md`.
- Componentes, diseño o límites de pantalla: actualizar `ARCHITECTURE.md`.
- Variables, build args, Docker o Nginx: actualizar `CONFIGURATION_AND_OPERATIONS.md`.
- Cobertura o suites ejecutadas: actualizar `TESTING.md`.
