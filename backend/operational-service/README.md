# KronFlow Operational Service (`backend/operational-service`)

Microservicio FastAPI de **KronFlow — Intelligent CRM** (*By BLANDSKRON*) que mantiene datos operacionales aislados en un schema PostgreSQL 18 por tenant (`tenant_schema_v21`, migraciones repetibles `v3–v21`). Expone lectura/escritura para el CRM, bandeja HITL, pipeline comercial, plataforma multi-agente, workflows DAG, Tool Hub/MCP, webchat, comercio/voz, campañas y privacidad, ingesta omnicanal durable y endpoints internos de aprovisionamiento, migración y contexto RAG.

## Capacidades reales

- Provisiona schemas `tenant_<slug>` con aislamiento estricto y registra su runtime en tablas públicas.
- Valida JWT RS256 emitidos por `auth-service` para APIs de dashboard y aplica permisos RBAC por recurso (`users.read`, `crm.manage`, `agents.create`, `audit.read`).
- Valida `X-Tenant-Code` + `X-Ingest-Key` para ingesta de canales y ejecuta outbox transaccional (`FK-03`), ledger de consentimiento (`FK-04`), turnos recuperables (`FK-02`/`FK-07`) y control HITL CAS (`FK-06`/`FK-19`).
- Administra contactos canónicos, captura pública (`FK-28`), pipeline de oportunidades con control optimista (`FK-29`), propuestas tipadas IA `at-most-once` (`FK-17`/`FK-18`), campañas/conexiones delegadas (`FK-23`/`FK-24`/`FK-30`), webhooks HMAC/SSRF (`FK-11`), adjuntos privados (`FK-13`), agenda (`FK-22`), eventos de dominio (`FK-10`), KPIs consolidados (`FK-09`) y ciclo de privacidad (`export`, `erase`, `retention`, `FK-27`).
- Persiste documentos y chunks de contexto empresarial consumidos por `agent-core` mediante endpoints `/internal/*` autenticados con `X-Internal-Token`.

Límites documentados:

- Los endpoints públicos `/api/v1/agents` administran el catálogo multi-agente con revisiones inmutables, reglas, trazas y handoff; la inferencia y el simulador viven en `agent-core` y las acciones supervisadas en `/api/v1/ai-proposals`.
- El rate limit de ingesta opera por proceso; producción requiere límites distribuidos en ingress.
- Suite automatizada contra PostgreSQL 18 verificable localmente (`python -m unittest discover -s tests -v`).

## Inicio local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env.local
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Antes de iniciar, sustituye todos los valores `replace-with-*`. Para Docker:

```powershell
Copy-Item .env.example .env.local
docker compose --env-file .env.local up --build
```

## URLs

- OpenAPI: `http://localhost:8001/openapi.json`
- Swagger: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`
- Liveness: `GET http://localhost:8001/healthz`
- Readiness DB: `GET http://localhost:8001/readyz`

`/readyz` ejecuta `SELECT 1`. Si la conexion falla, la excepcion no se captura actualmente y la respuesta puede ser 500, no `{"status":"not_ready"}`.

## Configuracion principal

| Variable | Proposito |
| --- | --- |
| `DATABASE_URL` | PostgreSQL compartido con la capa IAM |
| `INTERNAL_TOKEN` | Credencial de endpoints `/internal/*` |
| `JWT_PUBLIC_KEY` / `JWT_PUBLIC_KEY_PATH` | Clave publica de los JWT humanos de auth |
| `CORS_ALLOWED_ORIGINS` | Origenes web permitidos |
| `OPERATIONAL_PORT` | Puerto host de Compose; no lo lee FastAPI |

Settings adicionales disponibles en `.env.example` y `app/core/config.py`: `APP_NAME`, `ENVIRONMENT`, `DEBUG`, `DATABASE_SCHEMA`, `DATABASE_GRANT_ROLE`, `JWT_ALGORITHM`, `JWT_AUDIENCE`, `JWT_ISSUER`, `DEFAULT_PAGE_SIZE`, `MAX_PAGE_SIZE`, `TENANT_MIGRATION_VERSION` e `INGEST_RATE_LIMIT_PER_MINUTE`.

## Operaciones

```powershell
python scripts/provision_test_tenant.py --auth-tenant-id 1 --tenant-slug demo-tenant --plan starter
python scripts/migrate_all_tenants.py
python scripts/rotate_ingest_key.py 1
python scripts/validate_tenant_schema.py
python scripts/validate_demo_seed.py
```

Los scripts de validacion crean schemas temporales dentro de la base configurada; ejecutalos unicamente en una base descartable/autorizada.

Para tenants existentes, despues de agregar nuevas tablas tenant activas se debe ejecutar `python scripts/migrate_all_tenants.py` o `POST /internal/migrations/run-all`.

## Protocolo y licencia

Las fronteras entre servicios están en [ARCHITECTURE.md](../../ARCHITECTURE.md); las reglas agénticas y de validación viven en [AGENTS.md](../../AGENTS.md) y [.agents/skills/backend-multitenant/SKILL.md](../../.agents/skills/backend-multitenant/SKILL.md). Distribuido bajo [Apache License 2.0](../../LICENSE). No incluyas secretos, ingest keys ni datos personales en documentación o logs.
