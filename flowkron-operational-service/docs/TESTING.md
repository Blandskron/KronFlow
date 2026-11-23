# Testing y validación

## Estado real

`tests/test_contract_metadata.py` agrega cuatro pruebas sin DB para FK-09: empresa resuelta en éxito/error, prioridad sobre principal, compatibilidad de contexto previo y rechazo de cabeceras no verificadas como fuente de identidad. La prueba ASGI de FK-02 comprueba también `meta.tenant_id` en respuestas 200/409 y que permanece `null` ante credenciales inválidas (401).

Existen pruebas `unittest` en `tests/test_security.py` y `tests/test_message_identity.py`. La segunda valida FK-01 con PostgreSQL descartable; no necesita pytest. La dependencia de cliente HTTP declarada está en `requirements-dev.txt`.

FK-02 agrega `tests/test_turn_recovery.py`, con 13 pruebas PostgreSQL y API ASGI real. Reutiliza el fixture descartable de FK-01; no usa `TestClient` ni agrega dependencias. Cubre reclamación concurrente, persistencia atómica, expiración, respuesta/handoff, resultados desconocidos, confirmación idempotente, reconciliación, consentimiento antes del envío y credenciales/aislamiento. El fixture limita las consultas a 10 segundos para convertir bloqueos en fallos de prueba.

```powershell
python -m unittest discover -s tests -p test_turn_recovery.py -v
```

Con `FLOWKRON_TEST_POSTGRES_BIN` configurado, FK-02 aprobó sus 13 pruebas y FK-01 sus 9 pruebas. `npm test` en el conector aprobó 19 pruebas, incluidas nueve de fallos del pipeline. Sin la variable se omiten las pruebas PostgreSQL de ambas suites. No se conectó un canal real ni se ejecutó una migración sobre la instalación del usuario.

FK-03 agrega `test_turn_jobs.py` sobre el mismo cluster descartable. Termina un proceso después de que guarda una respuesta, adelanta el vencimiento de su lease de prueba y reclama la respuesta desde otro proceso. También prueba concurrencia, capacidad, aislamiento por cuenta y empresa, reversión transaccional, reprogramación y migración v4 a v5 repetible. El conector simulado prueba por separado el arranque y despacho sin reentrega.

FK-07 amplía las pruebas de cola y turnos con la migración de la tabla de evidencia, identidad reservada, recibos concurrentes y recuperación de envíos inciertos. La prueba del conector emite un recibo mientras espera el resultado de la llamada de envío simulada. El caso de Chromium comprueba las etiquetas de envío y el motivo de fallo. La validación usa PostgreSQL temporal y eventos de proveedor sintéticos.

```powershell
python -m unittest discover -s tests -p test_turn_jobs.py -v
```

### Búsqueda y lectura del inbox

`test_conversation_inbox.py` verifica búsqueda fuera de la primera página, cursor con llegadas nuevas, lectura monotónica y permisos de CRM. Su medición opcional crea 10.000 conversaciones y 100.000 mensajes sintéticos en PostgreSQL temporal. Mide 20 ejecuciones con caché caliente para la primera página y una búsqueda de contacto, e imprime `EXPLAIN (ANALYZE, BUFFERS)`. El presupuesto local es p95 inferior a 250 ms por consulta de listado de 40 conversaciones, incluido el total. La medición cubre el acceso al servicio Python y PostgreSQL local.

```powershell
$env:FLOWKRON_TEST_POSTGRES_BIN = 'C:/Program Files/PostgreSQL/18/bin'
$env:FLOWKRON_TEST_INBOX_BENCHMARK = '1'
python -m unittest discover -s tests -p test_conversation_inbox.py -v
```

Medición local del 19 de noviembre de 2026 en PostgreSQL 18 descartable.

| Consulta | p95 del servicio | `EXPLAIN ANALYZE` |
| --- | ---: | ---: |
| Primera página | 109,9 ms | 95,5 ms |
| Búsqueda «Contacto sintético 42» | 137,9 ms | 94,4 ms |

Los planes contaron 10.000 y 111 filas coincidentes mediante `WindowAgg` y ordenaron la página con `top-N heapsort` (29 kB). La consulta recuperó el resumen, contacto y lead completos para las 40 filas de cada página.

```powershell
python -m unittest discover -s tests -v
```

Para incluir las pruebas PostgreSQL, definir `FLOWKRON_TEST_POSTGRES_BIN` con el directorio de binarios instalados (`initdb` y `pg_ctl`) y ejecutar el mismo comando. El fixture de integración crea un clúster temporal en loopback y lo elimina al terminar. Para crear ese clúster prescinde de `DATABASE_URL`. Sin la variable se omiten las pruebas marcadas para PostgreSQL descartable.

```powershell
$env:FLOWKRON_TEST_POSTGRES_BIN = 'C:\Program Files\PostgreSQL\18\bin'
python -m unittest discover -s tests -p test_message_identity.py -v
```

Validación FK-01: 9 pruebas aprobadas (8 con PostgreSQL 18.3 y 1 de contrato de entrada). La suite del conector también aprobó sus 10 pruebas. Durante FK-01, `test_security.py` no se pudo importar porque la versión instalada de Starlette solicitaba `httpx2`, mientras `requirements-dev.txt` declaraba `httpx`.

El 22 de noviembre de 2026 se reprodujo el fallo del fixture de consentimiento del [job Validate](https://github.com/Blandskron/flowkron/actions/runs/44824257725) sobre `3e538686`. Tras corregir el fixture, la ejecución local de `python -m unittest discover -s tests -v` con PostgreSQL 18.3 descartable registró 57 pruebas aprobadas y una omitida, la medición opcional del inbox. Para que `TestClient` cargara con el Starlette 1.10.0 local, se usó `httpx2==2.16.2` desde un directorio temporal mediante `PYTHONPATH`.

### Integración PostgreSQL en Validate (FK-15)

El [workflow](../../.github/workflows/validate.yml) resuelve los binarios del runner con `pg_config --bindir` y verifica `initdb` y `pg_ctl` antes de ejecutar la suite. Cada clase abre su propio clúster temporal TCP en `127.0.0.1`. El fixture desactiva el socket Unix del clúster de prueba para permitir que un usuario sin privilegios ejecute PostgreSQL en Ubuntu.

```bash
export FLOWKRON_TEST_POSTGRES_BIN="$(pg_config --bindir)"
python -m unittest discover -s tests -v
python -c 'from app.main import app; assert app.openapi()["paths"]'
```

Validación del cambio sobre `c5da59a`: 57 aprobadas y una omitida en Ubuntu 24.04 con PostgreSQL 16.15 y las dependencias de `requirements-dev.txt`. La comprobación de OpenAPI pasó. En Windows con PostgreSQL 18.3 se repitió el mismo resultado de la suite con la dependencia de cliente temporal indicada arriba. En ambos casos el único skip fue el benchmark optativo. La ejecución en GitHub Actions para este cambio queda pendiente.

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
