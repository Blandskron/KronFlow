# KronFlow Deployment (`deploy/`)

El [Compose raíz](../compose.yaml) (`kronflow-stack`) incluye este directorio. Ejecuta `docker compose up --build --wait` desde la raíz del repositorio para levantar `auth-service`, `operational-service`, `agent-core`, `app`, `landing`, `postgres`, `redis`, `mail-service` y `baileys-services`. Para el entorno demo con el superusuario inicial de BLANDSKRON y contexto de ejemplo, usa `docker compose -f compose.demo.yaml up --build --wait`. Consulta [la guía raíz](../README.md) y [el historial de migración](../CHANGELOG.md).

## Módulos Compose

- `compose/bootstrap.yml`: servicio `init` que genera y preserva credenciales por volumen (`/bootstrap/*`).
- `compose/infrastructure.yml`: servicios `postgres` (PostgreSQL 18) y `redis` (Redis 7) sobre `kronflow-network`.
- `compose/backend.yml`: construye `auth-service`, `operational-service` y `agent-core` desde `../../backend/*` y comparte la clave pública JWT por volumen read-only.
- `compose/frontend.yml`: construye `landing` y `app` desde `../../frontend/*`.
- `compose/email.yml`: ejecuta `mail-service` sobre `kronflow-network` compartiendo Redis DB 1.
- `compose/whatsapp.yml`: ejecuta [baileys-services](../backend/baileys-services/README.md) en la red interna; las sesiones vinculadas persisten en `baileys-lab-sessions`.
- `.env.example`: overrides opcionales equivalentes a los de la raíz.

Valida ambas configuraciones con `docker compose --env-file .env.example config --quiet` y `docker compose -f compose.demo.yaml --env-file .env.example config --quiet`. Si un puerto local está ocupado, copia `.env.example` a `.env` y ajústalo. El despliegue incluido restringe puertos a loopback y modo local de desarrollo; antes de exponer en producción, revisa [docs/SECURITY.md](docs/SECURITY.md) y [docs/README.md](docs/README.md).
