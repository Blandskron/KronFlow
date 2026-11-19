# Operación y runbooks

## Arranque y smoke tests

```powershell
Copy-Item .env.example .env.local
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Validar `/healthz`, `/readyz`, `/openapi.json` y un request autenticado. `/healthz` no comprueba DB; `/readyz` puede ser 500 si DB no está disponible.

## Provisioning

Preferir la llamada desde auth service. Para prueba manual usa un token obtenido del ambiente, nunca uno documentado:

```http
POST /internal/tenants/provision
X-Internal-Token: <internal-token>
Content-Type: application/json

{"auth_tenant_id":1,"tenant_slug":"demo-tenant","plan":"starter"}
```

Guarda `ingest_key` inmediatamente: solo se devuelve en creacion. Repetir provisioning reaplica el schema tenant de forma idempotente y devuelve null, por lo que repara tablas faltantes sin emitir una key nueva.

Para recrear un tenant de desarrollo desde cero, envia `recreate_schema=true`; esto ejecuta `DROP SCHEMA ... CASCADE` sobre el schema persistido en `tenant_runtime` y luego reconstruye exclusivamente las tablas tenant activas.

## Migración de schemas

Para `tenant_schema_v4` (FK-02), seguir el [procedimiento de turnos recuperables](TURN_RECOVERY.md#migración-y-compatibilidad). Migrar Operational antes de reabrir el conector nuevo; revisar turnos en curso antes de volver al código anterior. Los resultados desconocidos se atienden con el [runbook de reconciliación](TURN_RECOVERY.md#reconciliación-operativa), sin forzar reenvíos.

Para `tenant_schema_v3` (FK-01), seguir el [procedimiento de identidad de mensajes](MESSAGE_IDENTITY.md#migración-y-operación): pausar tráfico, migrar antes de servir el nuevo modelo, revisar fallos y tratar schemas suspendidos antes de reactivarlos. La migración es aditiva, pero requiere locks e índices; no se aplica a una base existente por el mero arranque del proceso API.

```powershell
python scripts/migrate_all_tenants.py
```

El script escribe en todos los runtimes activos y registra resultados; no ejecutarlo por inspección. `POST /internal/migrations/run-all` hace lo mismo remotamente. Antes de un cambio tenant:

1. Probar en copia/DB descartable con varios schemas.
2. Clasificar si `create_all` basta (solo aditivo) o se requiere migración explícita.
3. Actualizar `TENANT_MIGRATION_VERSION` si cambia el estado esperado.
4. Planificar rollback y tenants parcialmente fallidos.
5. Ejecutar en ventana controlada y revisar `migration_registry`/`system_events`.

La migracion tambien crea tablas de contexto documental del agente en tenants existentes: `business_context_documents`, `document_chunks`, `document_embeddings`, `tenant_agent_profiles` y tablas asociadas de formularios. Debe ejecutarse despues de desplegar cambios que agreguen modelos tenant activos.

## Rotación de ingest key

```powershell
python scripts/rotate_ingest_key.py <auth_tenant_id>
```

O `POST /internal/tenants/{id}/rotate-ingest-key`. La key anterior se invalida en el commit y no hay solapamiento; coordina el cambio con el consumidor para evitar interrupción.


## Scripts de validación

- `validate_tenant_schema.py` crea `tenant_validation_tmp` y lo elimina con `DROP SCHEMA ... CASCADE` al inicio.
- `validate_demo_seed.py` hace lo mismo con `tenant_seed_validation_tmp` y ejecuta SQL de demo.
- `provision_test_tenant.py` crea datos persistentes normales.

Son escrituras/destrucciones DB. Úsalos solo con `DATABASE_URL` confirmado hacia una base de prueba; no son checks read-only.

## Runbook: JWT rechazado

1. Confirmar que `JWT_PUBLIC_KEY` o path estén configurados y accesibles.
2. Verificar que corresponda a la familia de JWT humano emitida por auth.
3. Revisar RS256, issuer, audience, expiración y `tenant_id`.
4. Si responde 404/402/403, revisar runtime/plan/status, no la firma.

## Runbook: ingest rechazada

1. 401: revisar tenant code/key y rotación reciente sin imprimir secretos.
2. 402: plan del runtime es Free/vacío.
3. 403: runtime no activo.
4. 429: límite por proceso; considerar también gateway.
5. 422: validar payload contra OpenAPI.

Si el error viene de un adaptador externo, revisa la conectividad, las credenciales y el contrato de ingesta.

## Runbook: schema inconsistente

1. Comparar `tenant_runtime`, schema físico y `migration_registry`.
2. Revisar `system_events` y logs, cuidando errores con datos sensibles.
3. Ejecutar validación en réplica/copia, no sobre tenant productivo.
4. Reaplicar migración solo si el cambio es idempotente; `create_all` no corrige columnas existentes.
5. Para cambios destructivos, preparar migración/rollback explícitos.

## Checklist de producción

- [ ] Sin defaults locales para DB/internal token; JWT y CORS correctos.
- [ ] Servicio/internal endpoints en red privada o protegidos por gateway/mTLS.
- [ ] Usuario DB con permisos mínimos compatibles con provisioning/migración.
- [ ] Backups y restore multi-schema probados.
- [ ] RBAC por endpoint resuelto en gateway o implementación antes de exponer dashboard sensible.
- [ ] Rate limit distribuido en gateway; no depender solo de memoria local.
- [ ] OpenAPI/Swagger restringidos según política.
- [ ] Alertas para 5xx, readiness, 401/403/429, fallos de provisioning/migración.
- [ ] Rotación de ingest/internal/JWT documentada y ensayada.
- [ ] Suite automatizada y pruebas cross-tenant antes de considerar madurez productiva.
