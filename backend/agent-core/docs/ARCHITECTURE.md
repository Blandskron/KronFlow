# Architecture

`flowkron-agent-core` es un servicio FastAPI alineado con la convencion de los servicios Flowkron:

- `app/main.py`: inicializacion FastAPI, middleware, routers y health checks.
- `app/core`: configuracion, seguridad, contratos, DB local/test y tenant context.
- `app/api/v1`: rutas publicas versionadas.
- `app/schemas`: exports de compatibilidad para DTOs publicos.
- `app/services`: facade de servicios de aplicacion.
- `app/models`: modelos SQLAlchemy usados solo en modo local/test o blueprint transversal.
- `docs`: documentacion operativa estandar.

La diferencia intencional frente a `flowkron-operational-service` es la capa IA:

- `app/application`: orquestacion del runtime conversacional.
- `app/domain`: puertos y contratos internos.
- `app/infrastructure`: adapters LLM, cliente interno hacia Operational, procesamiento documental y herramientas externas.

Operational decide tenant, industria y schema fisico. Agent Core no provisiona tenants ni decide donde escribir en produccion; consume contratos transversales y delega persistencia cuando `PERSISTENCE_MODE=operational`.

El contrato HTTP publico y el contrato interno usan envelopes estandarizados. Agent Core envuelve sus respuestas publicas mediante `api_contract_middleware`; cuando consume Operational, `OperationalContextClient` desempaqueta respuestas exitosas `{success,status,data,meta}` y retorna solo `data` hacia las rutas FastAPI para mantener validos los `response_model`.

## Flujo integrado de contexto empresarial

```text
Frontend privado
  -> Agent Core /api/v1/context/templates
  -> Agent Core /api/v1/context/documents/upload-file
       extrae texto y chunks
       -> Operational /internal/tenants/{tenant_id}/context/documents
            resuelve TenantRuntime
            aplica schema_translate_map
            persiste en tenant_<slug>.business_context_documents/document_chunks
            asigna la siguiente version si el filename ya existe para el tenant

Frontend privado
  -> Agent Core /api/v1/agent/simulate
       -> Operational /internal/tenants/{tenant_id}/context/retrieve
       <- fuentes con document_id/chunk_id/score
  <- respuesta, confianza, fuentes y accion
```

El core usa el `tenant_id` autenticado como identificador logico y `X-Internal-Token` para la llamada servicio-a-servicio. Nunca acepta `schema_name` desde el cliente ni lo calcula desde headers.

## Reglas de persistencia

- No existe persistencia in-memory de documentos/chunks/embeddings en modo operacional.
- `DATABASE_URL` y `ALLOW_LOCAL_DB_BOOTSTRAP=true` son solo para tests o desarrollo aislado.
- Si el contenedor se recrea, el estado empresarial debe seguir existiendo porque vive en PostgreSQL mediante Operational.
- Si PostgreSQL no contiene documentos, el status y el simulador deben reflejar ausencia de contexto.
- Las mutaciones directas de documentos (`GET` individual, `PATCH`, `DELETE`), reglas (`agent_rules`), trazas (`agent_execution_traces`), sesiones de onboarding (`setup_chat_sessions`), resolución de agente activo, memoria escoped, creación de propuestas CRM y registro de consumo/costos IA delegan en Operational vía `/internal/tenants/{tenant_id}/context/*` cuando `PERSISTENCE_MODE=operational`. En `/api/v1/agent/messages` se registran propuestas y uso con `is_simulation=false`; `/api/v1/agent/simulate` omite efectos CRM y marca trazas y uso con `is_simulation=true`. Los formularios estructurados locales siguen reservados para entorno de desarrollo aislado.
