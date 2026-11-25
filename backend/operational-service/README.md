# flowkron-operational-service

Microservicio FastAPI que mantiene datos operacionales aislados en un schema PostgreSQL por tenant. Expone lectura/escritura para el dashboard, ingesta WhatsApp para automatizaciones y endpoints internos de aprovisionamiento, migracion y contexto del agente.

## Capacidades reales

- Provisiona schemas `tenant_<slug>` y registra su runtime en tablas publicas.
- Valida JWT RS256 humanos emitidos por `flowkron-auth-service` para APIs de dashboard.
- Valida `X-Tenant-Code` + `X-Ingest-Key` para ingesta WhatsApp.
- Ingresa mensajes idempotentes, clasificacion de leads, handoffs y estados.
- Lista/actualiza leads, conversaciones, mensajes y metricas.
- Expone ocho colecciones operacionales para el frontend: clientes, leads, inventario, conversaciones, mensajes, solicitudes de derechos, ejecutivos y log de limpiezas.
- Provisiona y persiste contexto documental de Agent Core dentro del schema tenant activo: documentos, chunks, embeddings futuros y perfil del agente.
- Expone endpoints internos para que Agent Core cree/lista documentos, consulte status y recupere fuentes RAG sin conocer `schema_name`.
- Migra todos los runtimes activos mediante creacion idempotente de tablas/vistas/triggers.

Limites importantes:

- Los endpoints publicos `/api/v1/agents` son stubs: listar devuelve `[]`, configurar responde 501 y actualizar termina en 404. Esto no afecta los endpoints internos de contexto usados por Agent Core.
- Los routers JWT validan firma/tenant/plan, pero actualmente no aplican permisos RBAC especificos aunque existe `require_permission`.
- El rate limit de ingest es en memoria por proceso; no es distribuido ni persistente.
- No existe suite automatizada versionada.

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

Settings adicionales disponibles: `APP_NAME`, `ENVIRONMENT`, `DEBUG`, `DATABASE_SCHEMA`, `DATABASE_GRANT_ROLE`, `JWT_ALGORITHM`, `JWT_AUDIENCE`, `JWT_ISSUER`, `DEFAULT_PAGE_SIZE`, `MAX_PAGE_SIZE`, `TENANT_MIGRATION_VERSION` e `INGEST_RATE_LIMIT_PER_MINUTE`. Consulta [Configuracion](docs/CONFIGURATION.md).

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

## Documentacion

Consulta [docs/README.md](docs/README.md) para arquitectura, API, datos, seguridad, operacion y testing. Las instrucciones agenticas estan consolidadas en [AGENTS.md](AGENTS.md).

## Propiedad

See the repository license for distribution terms. Consulta [LICENSE](../LICENSE). No incluyas secretos, ingest keys ni datos personales en documentacion o logs.
