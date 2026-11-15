# Documentación de flowkron-operational-service

Documentación mantenida contra la implementación. OpenAPI (`/openapi.json`) es la referencia generada para schemas HTTP; estos documentos explican límites, seguridad y operación.

| Documento | Contenido |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Componentes, aislamiento y flujos |
| [API.md](API.md) | Inventario de endpoints y autenticación |
| [DATA_MODEL.md](DATA_MODEL.md) | Tablas públicas/tenant activas y legado no importado |
| [CONFIGURATION.md](CONFIGURATION.md) | Variables, defaults y Docker |
| [SECURITY.md](SECURITY.md) | Controles implementados y brechas explícitas |
| [OPERATIONS.md](OPERATIONS.md) | Provisioning, migraciones, runbooks y producción |
| [TESTING.md](TESTING.md) | Validación actual y cobertura pendiente |

Las instrucciones para agentes están consolidadas en [../AGENTS.md](../AGENTS.md); no existe una copia paralela bajo `docs/agent/`.

## Regla de mantenimiento

- Router/schema Pydantic: actualizar `API.md` y OpenAPI.
- Modelo público o tenant: actualizar `DATA_MODEL.md` y estrategia de migración.
- Setting/Compose: actualizar `CONFIGURATION.md` y `.env.example`.
- Resolver, auth, schema mapping o secrets: actualizar `SECURITY.md`, pruebas y `AGENTS.md`.
- No describir los módulos legacy de `tenant_models/` ni endpoints stub como funcionalidad activa.
