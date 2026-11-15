# Documentación de flowkron-auth-service

Documentación mantenida contra la implementación. El esquema de `/api/schema/` es la referencia generada para payloads; estos documentos explican decisiones, invariantes y operación.

| Documento | Contenido |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Responsabilidades, límites y flujos |
| [ADR.md](ADR.md) | Decisiones arquitectónicas |
| [API.md](API.md) | Inventario HTTP y autorización |
| [CONSUMPTION_GUIDE.md](CONSUMPTION_GUIDE.md) | Patrones para frontend y servicios consumidores |
| [DATA_MODEL.md](DATA_MODEL.md) | Tablas, estados e invariantes |
| [SECURITY.md](SECURITY.md) | Controles implementados y brechas explícitas |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Configuración, Docker y entrypoint |
| [OPERATIONS.md](OPERATIONS.md) | Operación, checklist y runbooks consolidados |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Desarrollo local y convenciones |
| [TESTING.md](TESTING.md) | Cobertura real y brechas |
| [LEGAL_AND_ACCEPTABLE_USE.md](LEGAL_AND_ACCEPTABLE_USE.md) | Propiedad y uso aceptable |

Las instrucciones para agentes están consolidadas en [../AGENTS.md](../AGENTS.md); no se mantiene una segunda copia bajo `docs/agent/`.

## Regla de actualización

- Cambio de endpoint o serializer: actualizar OpenAPI y `API.md`.
- Cambio de modelo/migración: actualizar `DATA_MODEL.md`.
- Cambio de variable o arranque: actualizar `.env.example`, `DEPLOYMENT.md` y, si afecta agentes, `AGENTS.md`.
- Cambio de control de seguridad: actualizar `SECURITY.md` y pruebas.
- No documentar recomendaciones futuras como capacidades ya implementadas.
