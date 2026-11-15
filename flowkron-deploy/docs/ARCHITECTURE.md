# Arquitectura

## Modelo Compose

`docker-compose.yml` define `name: flowkron-stack` e incluye infraestructura, backends y frontends.

> [!NOTE]

```text
Browser
  -> :8080 landing (Nginx)
  -> :8081 app (Nginx)
  -> :8000 auth (Django)
  -> :8001 operational (FastAPI)
  -> :8002 agent-core (FastAPI)

flowkron-network
  -> postgres:5432  <- auth + operational
  -> redis:6379     <- auth
  -> auth:8000      -> operational:8001
  -> agent-core:8002 -> operational:8001
```


La red bridge facilita DNS interno, pero los puertos publicados siguen expuestos al host.

## Dependencias

1. PostgreSQL y Redis no dependen de otros servicios.
2. Auth declara `depends_on` solo de Redis saludable; su entrypoint espera PostgreSQL usando `DATABASE_URL`.
3. Operational espera auth saludable; recibe la publica JWT por bind mount RO y usa PostgreSQL mediante `OPERATIONAL_DATABASE_URL`.
4. Agent Core espera auth y operational saludables; recibe la publica JWT por bind mount RO y delega persistencia a Operational.
5. App espera auth saludable, pero debe poder alcanzar Operational y Agent Core desde el navegador.
6. Landing inicia de forma independiente.

`depends_on` ordena inicio/health inicial; no garantiza readiness funcional continua.

## Persistencia

| Recurso | Tipo | Uso |
| --- | --- | --- |
| `flowkron-postgres-18-cluster` | Named volume | Datos PostgreSQL |
| `flowkron-redis-data` | Named volume | Redis |
| `data/jwt-keys` | Bind mount | Auth RW; operational/agent-core RO |
| `data/auth-media` | Bind mount | Media de auth |

`docker compose down` preserva datos. `down -v` borra named volumes.

## Base de datos

Auth y Operational apuntan por defecto al mismo servidor y database `flowkron_auth`, usando drivers/URLs distintos. Agent Core no recibe `DATABASE_URL` en el stack integrado y no crea schemas ni tablas; cualquier persistencia de contexto/RAG debe pasar por Operational.

Operational resuelve tenant, schema fisico y futura variante por industria. El aislamiento logico y migraciones pertenecen a los servicios duenios; este Compose no crea databases separadas.

## Contexto Empresarial

El flujo integrado es:

```text
Browser -> flowkron-front-app-angular -> flowkron-agent-core -> flowkron-operational-service -> PostgreSQL tenant schema
```

El navegador nunca llama endpoints `/internal/*`. Agent Core extrae texto/chunks y llama a Operational con `X-Internal-Token`. Operational resuelve `TenantRuntime`, aplica `schema_translate_map` y escribe en tablas como:

- `tenant_<slug>.business_context_documents`
- `tenant_<slug>.document_chunks`
- `tenant_<slug>.document_embeddings`
- `tenant_<slug>.tenant_agent_profiles`

Despues de agregar tablas tenant activas, los tenants existentes requieren `POST /internal/migrations/run-all` o el script equivalente de Operational.

## Healthchecks

- PostgreSQL: `pg_isready`.
- Redis: `redis-cli ping`.
- Auth: `GET /healthz/`.
- Operational: `GET /healthz`.
- Agent Core: `GET /health`.
- Landing: `GET /`.
- App: `GET /login`.

Son liveness/readiness superficiales; no prueban login, migraciones correctas, SMTP, flujos operacionales ni consistencia de datos.
