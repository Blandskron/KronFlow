# KronFlow Deployment (`deploy/`)

El [Compose raíz](../compose.yaml) (`kronflow-stack`) incluye este directorio. Ejecuta `docker compose up --build --wait` desde la raíz del repositorio para levantar `auth-service`, `operational-service`, `agent-core`, `app`, `landing`, `postgres`, `redis`, `mail-service` y `baileys-services`. Para el entorno demo con el superusuario inicial de BLANDSKRON y contexto de ejemplo, usa `docker compose -f compose.demo.yaml up --build --wait`. Consulta [la guía raíz](../README.md) y [el historial de migración](../CHANGELOG.md).

## Módulos Compose

- `compose/bootstrap.yml`: servicio `init` que genera y preserva credenciales por volumen (`/bootstrap/*`).
- `compose/infrastructure.yml`: servicios `postgres` (PostgreSQL 18) y `redis` (Redis 7) sobre `kronflow-network`.
- `compose/backend.yml`: construye `auth-service`, `operational-service`, `operational-worker` y `agent-core` desde `../../backend/*` y comparte la clave pública JWT por volumen read-only.
- `compose/frontend.yml`: construye `landing` y `app` desde `../../frontend/*`.
- `compose/email.yml`: ejecuta `mail-service` sobre `kronflow-network` compartiendo Redis DB 1.
- `compose/whatsapp.yml`: ejecuta [baileys-services](../backend/baileys-services/README.md) en la red interna; las sesiones vinculadas persisten en `baileys-lab-sessions`.
- `.env.example`: overrides opcionales equivalentes a los de la raíz.

## Validación y seguridad

```sh
docker compose --env-file .env.example config --quiet
docker compose -f compose.demo.yaml --env-file .env.example config --quiet
```

- **Smoke E2E descartable:** `docker compose -f compose.yaml -p kronflow-smoke up --build --wait --wait-timeout 180 && python deploy/bootstrap/smoke.py kronflow-smoke --standard` (y repetir con `compose.demo.yaml` sin `--standard`; desmontar con `docker compose ... -p kronflow-smoke down`).
- **Seguridad:** nunca ejecutes `docker compose config` sin `--quiet` en logs compartidos (puede exponer secretos), nunca montes la clave privada JWT en `operational-service` o `agent-core`, y recuerda que los defaults incluidos están pensados para desarrollo en loopback. Antes de producción revisa [RELEASE_READINESS.md](../RELEASE_READINESS.md), [AGENTS.md](../AGENTS.md) y [.agents/skills/compose-deploy-and-ci/SKILL.md](../.agents/skills/compose-deploy-and-ci/SKILL.md).
