# Testing y validación

## Estado real

No existen archivos `test_*.py`/`tests.py` ni dependencias de testing en `requirements.txt`. `pyproject.toml` conserva una configuracion pytest placeholder (`testpaths = ["app/tests", "tests"]`), pero esas rutas no tienen specs versionados. Los scripts bajo `scripts/` son utilidades manuales con DB real, no tests automatizados y algunos ejecutan DDL destructivo sobre schemas temporales.

## Validaciones read-only

```powershell
python -m compileall -q app scripts
```

También puede importarse `app.main` si las dependencias están instaladas y `DATABASE_URL` es parseable; el engine se crea al importar, aunque la conexión efectiva ocurre en startup/request.

La revisión documental debe usar `git diff --check`, enlaces relativos y búsqueda de referencias obsoletas.

## Validaciones con DB descartable

Solo con autorización y URL confirmada:

```powershell
python scripts/validate_tenant_schema.py
python scripts/validate_demo_seed.py
python scripts/provision_test_tenant.py --auth-tenant-id 1 --tenant-slug test-tenant
python scripts/migrate_all_tenants.py
```

Estas validaciones no tienen assertions automatizadas ni limpieza uniforme; inspecciona salida/DB y no declares una suite aprobada.

## Cobertura prioritaria pendiente

- JWT inválido, issuer/audience, tenant ausente y clave no configurada.
- Internal token e ingest key correctos/incorrectos.
- Aislamiento cross-tenant en lectura, actualización e ingest.
- Sanitización, colisiones y longitud de schemas.
- Runtime missing/suspended/Free.
- Idempotencia concurrente de mensajes/provisioning.
- Límite ingest y comportamiento multi-worker.
- Fallos transaccionales parciales de provisioning/migration.
- Contratos de leads/conversations y campos aceptados pero no persistidos.
- Endpoints operacionales y filtros/paginación.
- Agentes deben mantener explícitamente 501/404 hasta implementación.
- Readiness con DB caída.

## Estrategia recomendada

Agregar pytest, FastAPI TestClient/httpx y fixtures PostgreSQL reales por schema. Mockear validación JWT donde corresponda, pero conservar pruebas de integración criptográfica. Cada test debe usar schemas únicos y cleanup seguro; nunca apuntar a DB compartida/productiva.
