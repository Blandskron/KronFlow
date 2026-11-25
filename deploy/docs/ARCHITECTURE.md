# Arquitectura

## Modelo Compose

`docker-compose.yml` define `name: kronflow-stack` e incluye inicialización (`init`), infraestructura (`postgres`, `redis`), backends (`auth-service`, `operational-service`, `agent-core`), frontends (`landing`, `app`), correo (`mail-service`) y Baileys (`baileys-services`).

```text
Browser
  -> :8080 landing (Nginx)
  -> :8081 app (Nginx)
  -> :8000 auth-service (Django)
  -> :8001 operational-service (FastAPI)
  -> :8002 agent-core (FastAPI)

kronflow-network
  -> postgres:5432            <- auth-service + operational-service
  -> redis:6379               <- auth-service + mail-service
  -> auth-service:8000        -> operational-service:8001
  -> agent-core:8002          -> operational-service:8001
```


La red bridge facilita DNS interno, pero los puertos publicados siguen expuestos al host.

## Dependencias

1. Init guarda la configuración de cada servicio y termina. PostgreSQL y Baileys esperan ese resultado. Redis inicia en paralelo.
2. Operational espera que PostgreSQL acepte conexiones TCP. Su readiness comprueba una consulta real.
3. Auth espera PostgreSQL, Redis y Operational. Aplica migraciones, prepara las claves JWT y aprovisiona el primer workspace en un proyecto local vacío.
4. Agent Core espera Auth y Operational. En modo integrado, su readiness depende de Operational.
5. La app espera los tres backends. La landing espera Auth para el formulario de contacto.

`depends_on` ordena inicio/health inicial; no garantiza readiness funcional continua.

## Persistencia

| Recurso | Tipo | Uso |
| --- | --- | --- |
| `kronflow-postgres-18-cluster` | Named volume | Datos PostgreSQL |
| `kronflow-redis-data` | Named volume | Redis |
| `kronflow-jwt-keys`, `kronflow-jwt-public` | Named volumes | Clave privada en Auth. Clave pública de verificación en Operational y Agent Core |
| `kronflow-auth-media` | Named volume | Media de Auth |
| `kronflow-*-config` | Named volumes | Credenciales iniciales por servicio |
| `baileys-lab-sessions` | Named volume | Sesión vinculada de Baileys |

`docker compose down` preserva datos. `down -v` borra named volumes.

## Base de datos

Auth y Operational apuntan por defecto al mismo servidor y database `flowkron_auth`, usando drivers/URLs distintos. Agent Core no recibe `DATABASE_URL` en el stack integrado y no crea schemas ni tablas; cualquier persistencia de contexto/RAG debe pasar por Operational.

Operational resuelve tenant, schema fisico y futura variante por industria. El aislamiento logico y migraciones pertenecen a los servicios duenios; este Compose no crea databases separadas.

## Contexto Empresarial

El flujo integrado es:

```text
Browser -> frontend/app -> agent-core -> operational-service -> PostgreSQL tenant schema
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
- Operational: `GET /readyz`.
- Agent Core: `GET /ready`.
- Landing: `GET /`.
- App: `GET /login`.

El [smoke test](VALIDATION.md) comprueba login, aprovisionamiento, datos del tenant, simulación y contacto después del arranque.
