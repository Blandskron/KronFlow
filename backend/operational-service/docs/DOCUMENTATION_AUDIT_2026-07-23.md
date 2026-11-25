# Auditoría documental — 2026-07-23

> Historical record. The former bundled channel workflow was removed in the Flowkron transition. For the current topology, see the repository architecture.

Se contrastaron routers FastAPI, schemas, modelos activos, configuración pública, OpenAPI y scripts.

## Hechos confirmados

- El aislamiento usa `schema_translate_map`; el schema tenant no debe llegar desde una API pública.
- `tenant_models/operations.py` y `context.py` son el modelo activo; otros módulos tenant son legado no provisionado.
- Dashboard valida JWT, tenant activo y plan pagado, pero no aplica RBAC granular por router.
- `/api/v1/agents` existe, aunque no persiste agentes; el flujo no es una capacidad terminada.
- Las rutas `/api/v1/ingest/whatsapp/*` están publicadas con tenant code/key, pero el flujo de canal anterior exportado aún usa Postgres directo legado.
- No hay suite automatizada ni pytest instalado.

Las fuentes canónicas son el índice `docs/README.md`, OpenAPI y los documentos por dominio. No se ejecutaron scripts que escriben o eliminan schemas.
