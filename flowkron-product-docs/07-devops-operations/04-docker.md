# Docker y Compose

Versión: 1.2
Tipo: estado actual
Estado: `IMPLEMENTED` para integración local
Última verificación: 2026-07-23

## Archivos

| Archivo | Contenido |
| --- | --- |
| `docker-compose.yml` | Incluye infraestructura, backend y frontend |
| `compose/infrastructure.yml` | PostgreSQL, Redis, volúmenes y red |
| `compose/backend.yml` | Auth, Operational y Agent Core |
| `compose/frontend.yml` | Landing y App |

## Comportamiento

- Todos los servicios comparten `flowkron-network`.
- PostgreSQL/Redis persisten en named volumes.
- Auth monta claves/media; consumidores montan la clave pública.
- URLs de frontend son build args públicos.
- Los healthchecks son superficiales.
- `depends_on` ordena inicio, no garantiza disponibilidad continua.

## Seguridad

El stack publica puertos al host, usa HTTP y defaults de desarrollo. No expandir ni registrar `docker compose config` porque puede mostrar secretos; use `docker compose config --quiet`.

No ejecutar `down -v`, prune, rotación/borrado de claves o migraciones destructivas sin respaldo y autorización.
