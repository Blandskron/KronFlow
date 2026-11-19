# Testing y validación

## Estado real

Existen pruebas `unittest` en `tests/test_security.py` y `tests/test_message_identity.py`. La segunda valida FK-01 con PostgreSQL descartable; no necesita pytest. La dependencia de cliente HTTP declarada está en `requirements-dev.txt`.

```powershell
python -m unittest discover -s tests -v
```

Para incluir las pruebas PostgreSQL, definir `FLOWKRON_TEST_POSTGRES_BIN` con el directorio de binarios instalados (`initdb` y `pg_ctl`) y ejecutar el mismo comando. La suite crea un cluster nuevo temporal en loopback y lo elimina al terminar; no usa `DATABASE_URL`. Sin esa variable se omiten explícitamente las ocho pruebas de integración, no se reportan como aprobadas.

```powershell
$env:FLOWKRON_TEST_POSTGRES_BIN = 'C:\Program Files\PostgreSQL\18\bin'
python -m unittest discover -s tests -p test_message_identity.py -v
```

Validación FK-01: 9 pruebas aprobadas (8 con PostgreSQL 18.3 y 1 de contrato de entrada). La suite del conector también aprobó sus 10 pruebas. El intento de ejecutar toda la suite Operational encontró una limitación previa del entorno: `test_security.py` no se pudo importar porque la versión instalada de Starlette solicita `httpx2`, mientras `requirements-dev.txt` declara `httpx`. No se cambiaron dependencias en FK-01. Esta suite completa queda sin validar hasta resolver esa compatibilidad.

Los scripts bajo `scripts/` son utilidades manuales y no deben ejecutarse contra una base compartida por inspección. La [decisión FK-01](MESSAGE_IDENTITY.md) detalla las verificaciones de migración, compatibilidad y concurrencia.

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
