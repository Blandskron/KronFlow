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

### Evidencia de consentimiento de WhatsApp (FK-04)

`test_contact_consent.py` verifica el permiso de auditoría, el aislamiento por empresa y schema, la consulta sobre registros anteriores a v8 y la paginación sin alterar el estado vigente. También carga dos veces el fixture de consentimiento y comprueba que quede un contacto con 16 eventos.

```powershell
$env:FLOWKRON_TEST_POSTGRES_BIN = 'C:/Program Files/PostgreSQL/18/bin'
python -m unittest discover -s tests -p test_contact_consent.py -v
```

### Elegibilidad de campañas (FK-04 y FK-30)

`tests/test_campaign_eligibility.py` y `tests/test_campaigns_and_channels.py` cubren aislamiento, vigencia y orden de decisiones, supresión por finalidad, reevaluación del snapshot, worker stub y recibos deduplicados.

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

El 22 de noviembre de 2026 se reprodujo el fallo del fixture de consentimiento del [job Validate](https://github.com/Blandskron/KronFlow/actions/runs/44824257725) sobre `3e538686`. Tras corregir el fixture, la ejecución local de `python -m unittest discover -s tests -v` con PostgreSQL 18.3 descartable registró 57 pruebas aprobadas y una omitida, la medición opcional del inbox. Para que `TestClient` cargara con el Starlette 1.10.0 local, se usó `httpx2==2.16.2` desde un directorio temporal mediante `PYTHONPATH`.

### Integración PostgreSQL en Validate (FK-15)

El [workflow](../../.github/workflows/validate.yml) resuelve los binarios del runner con `pg_config --bindir` y verifica `initdb` y `pg_ctl` antes de ejecutar la suite. Cada clase abre su propio clúster temporal TCP en `127.0.0.1`. El fixture desactiva el socket Unix del clúster de prueba para permitir que un usuario sin privilegios ejecute PostgreSQL en Ubuntu.

```bash
export FLOWKRON_TEST_POSTGRES_BIN="$(pg_config --bindir)"
python -m unittest discover -s tests -v
python -c 'from app.main import app; assert app.openapi()["paths"]'
```

Validación del cambio sobre `c5da59a`: 57 aprobadas y una omitida en Ubuntu 24.04 con PostgreSQL 16.15 y las dependencias de `requirements-dev.txt`. La comprobación de OpenAPI pasó. En Windows con PostgreSQL 18.3 se repitió el mismo resultado de la suite con la dependencia de cliente temporal indicada arriba. En ambos casos el único skip fue el benchmark optativo.

En `c65a364`, GitHub Actions ejecutó Operational con PostgreSQL 18.7. Pasaron 61 pruebas y la comprobación de OpenAPI, con una omisión correspondiente al benchmark optativo. Los jobs de arranque estándar y demo también terminaron con éxito en esa revisión. [Job de Operational](https://github.com/Blandskron/KronFlow/actions/runs/45077569420/job/137378120307) · [Validate](https://github.com/Blandskron/KronFlow/actions/runs/45077569420)

### Perfil de puntos de contacto (FK-28)

Desde la raíz del servicio, ejecutar el diagnóstico con un CSV UTF-8 de datos sintéticos o de una copia anonimizada autorizada. Usar un archivo por empresa y una fila por contacto con columnas `email` y `phone`. Para preservar las colisiones al anonimizar, conservar clases de equivalencia, casos ambiguos y ausencias.

```powershell
python -m scripts.profile_contact_points C:/ruta/aislada/contactos-sinteticos.csv
```

El JSON cuenta filas, valores ausentes, formatos sin resolver y valores normalizados por tipo. `duplicate_values` cuenta los valores normalizados que se repiten y `contacts_with_duplicates` cuenta las filas implicadas por tipo. Solo imprime agregados y usa las mismas reglas que la ficha y `test_capture_and_events.py`.

Validación local del 23 de noviembre de 2026. Pasaron 65 pruebas de Operational con PostgreSQL 18 descartable y se omitió el benchmark opcional. Se comprobó el JSON del diagnóstico con un CSV sintético y se validó OpenAPI. Pasaron cinco pruebas de Chromium con respuestas de API simuladas, incluidas la visualización de datos normalizados y la compatibilidad con la respuesta anterior. [Pruebas de Chromium](../../flowkron-front-app-angular/tests/visual/flowkron-front.visual.spec.ts)

### Plan de backfill de solo lectura (FK-28)

Usar una fila por contacto de una sola empresa, con `contact_id`, `email` y `phone`. El ID debe ser un entero positivo único dentro del rango `bigint`.

```powershell
python -m scripts.profile_contact_points --plan C:/ruta/aislada/contactos-sinteticos.csv
```

Por tipo de punto, `eligible` identifica IDs con un valor normalizado inequívoco en esa muestra. `collisions` agrupa IDs que reclaman el mismo valor normalizado y `unresolved` señala formatos que requieren revisión. Un teléfono conflictivo no invalida un correo inequívoco del mismo contacto. Las filas se pueden entregar en cualquier orden con el mismo resultado. El plan emite IDs y omite los valores del correo y teléfono. Usar la salida para revisar candidatos dentro del mismo contexto autorizado que el CSV. Persistir puntos y ejecutar el backfill sigue pendiente.

### Actividad diaria y restauración lógica

`test_analytics_activity.py` verifica el endpoint ASGI con dos empresas, control de permiso, rango inválido y cambio de hora de otoño. También comprueba los ceros y el corte parcial. `test_operational_restore.py` restaura una copia cifrada con dos schemas en PostgreSQL descartable y verifica referencias, aislamiento, consentimiento, deduplicación y nuevas escrituras. `test_tenant_upgrade_matrix.py` modela seis perfiles históricos v3–v8, ejecuta dos veces el migrador actual y prueba rollback transaccional ante un fallo en un runtime suspendido. Los perfiles son fixtures sintéticos de compatibilidad. Queda ensayar backups del despliegue candidato. [Ensayo y límites de restauración](OPERATIONS.md#ensayo-de-restauración-multiempresa)

### Seguimiento comercial manual

`test_lead_workflow.py` carga dos veces el mismo contacto sintético y comprueba que conserva su ID, carece de canal y mantiene el consentimiento desactivado. Con PostgreSQL descartable verifica permisos, colisiones de IDs entre empresas, reutilización del lead cuando la ingesta y un operador compiten, versión de cambios e historial filtrado.

`test_manual_contacts.py` prueba alta simultánea con el mismo UUID, repetición después de editar, normalización, valores opcionales, conflicto de edición, auditoría sin copiar datos de contacto y aislamiento de empresas. El recorrido desde la interfaz usa el mismo contrato que la API ASGI.

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
