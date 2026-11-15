# Runbook

Levantar local:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

Instalar dependencias:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Por defecto el servicio corre con `PERSISTENCE_MODE=operational` y no crea tablas. Para tests aislados puede activarse `ALLOW_LOCAL_DB_BOOTSTRAP=true`, pero no debe usarse en stack integrado.

Validar salud:

```powershell
Invoke-WebRequest http://127.0.0.1:8002/health
Invoke-WebRequest http://127.0.0.1:8002/ready
```

Correr tests:

```powershell
.\.venv\Scripts\python.exe -m pytest app\tests
```

Migraciones: no se ejecutan desde `flowkron-agent-core`. Operational provisiona el DDL real por tenant/schema.

Depuracion comun:

- `401 Missing authenticated tenant`: enviar JWT o `X-Tenant-Id` en local.
- `403 Payload tenant does not match`: el `tenant_id` del body no coincide con el autenticado.
- Respuesta con baja confianza: cargar documento activo o formulario antes de simular.
- `ResponseValidationError` despues de llamar Operational: reconstruir/recrear `flowkron-agent-core`; debe desempaquetar `ApiResponse.data`.
- `UniqueViolation` por `uniq_document_tenant_filename_version`: reconstruir/recrear `flowkron-operational-service`; debe asignar la siguiente version para filenames repetidos.

Validar endpoint universal:

```powershell
Invoke-WebRequest -Method Post http://127.0.0.1:8002/api/v1/agent/messages -Headers @{"X-Tenant-Id"="demo"} -ContentType "application/json" -Body '{"channel":"webchat","conversation_id":"c1","customer":{"external_id":"u1"},"message":{"type":"text","content":"hola","attachments":[]},"metadata":{"raw_payload":{}}}'
```
