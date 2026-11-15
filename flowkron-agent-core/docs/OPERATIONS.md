# Operations

Ejecucion local:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

Health checks:

- `GET /health`
- `GET /ready`

Docker instala desde `requirements.txt`. En despliegue integrado, el servicio debe arrancar con `PERSISTENCE_MODE=operational`, `ALLOW_LOCAL_DB_BOOTSTRAP=false`, `OPERATIONAL_SERVICE_URL` e `INTERNAL_TOKEN`.

## Contexto empresarial integrado

Si el front muestra documentos pero PostgreSQL no, el contenedor probablemente no fue recreado despues de actualizar la imagen o se esta consultando un entorno distinto. En la version actual no existe ruta in-memory para documentos/chunks en modo operacional.

Checklist:

1. Reconstruir y recrear `flowkron-operational-service` y `flowkron-agent-core`.
2. Ejecutar `POST /internal/migrations/run-all` o el comando equivalente de Operational para crear tablas nuevas en tenants existentes.
3. Verificar que existan `tenant_<slug>.business_context_documents` y `tenant_<slug>.document_chunks`.
4. Volver a subir los documentos desde el frontend; documentos subidos antes de la migracion/integracion no se migran desde memoria.
5. Probar `/api/v1/context/status` y `/api/v1/agent/simulate` contra el tenant autenticado.

## Diagnostico rapido

- Status con cero documentos y DB con cero documentos: estado consistente, falta carga.
- Status con documentos y DB con cero documentos: runtime viejo, entorno equivocado o proxy apuntando a otro `agent-core`.
- Simulador con cero fuentes y documentos existentes: pregunta sin match lexical, documentos inactivos o chunks no creados.
- 401/403 desde Agent Core hacia Operational: revisar `INTERNAL_TOKEN` y runtime tenant activo.
- 500 en `upload-file` con `UniqueViolation` sobre `uniq_document_tenant_filename_version`: Operational esta corriendo una imagen vieja o un flujo que intenta reutilizar `version=1`; reconstruir/recrear `flowkron-operational-service` para usar versionado automatico por filename.
- `ResponseValidationError` con campos `success/status/data/meta` en Agent Core: el contenedor corre una imagen vieja sin desempaquetado del envelope de Operational; reconstruir/recrear `flowkron-agent-core`.

Validacion de Docker local:

```powershell
docker compose build flowkron-operational-service flowkron-agent-core
docker compose up -d flowkron-operational-service flowkron-agent-core
docker compose logs --tail 100 flowkron-operational-service
docker compose logs --tail 100 flowkron-agent-core
```
