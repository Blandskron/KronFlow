# Data Schema

Las entidades de este documento son blueprints transversales de `flowkron-agent-core`. El core no crea bases de datos ni schemas en produccion. `flowkron-operational-service` resuelve `tenant_runtime`, `schema_name`, variante por industria y aplica las migraciones/DDL correspondientes.

Todas las tablas operativas del core incluyen `tenant_id` como defensa logica adicional, aun cuando vivan dentro de un schema fisico tenant/industria.

Modelos principales:

- `TenantAgentProfile`: perfil, tono, estado y resumen del agente por tenant.
- `BusinessContextDocument`: documento cargado, estado, prioridad, version y texto extraido.
- `DocumentChunk` y `DocumentEmbedding`: unidades de recuperacion y vector futuro.
- `BusinessContextTemplate`: catalogo global de plantillas por formato.
- `BusinessContextForm`, `BusinessContextField`, `BusinessContextFormSubmission`: formularios base y respuestas.
- `ConversationSession` y `ConversationMessage`: memoria conversacional local/test; en integrado las conversaciones operacionales viven en `flowkron-operational-service`.
- `AgentRule`, `AgentPolicy`, `AgentTool`: reglas, politicas y herramientas permitidas.
- `AgentActionLog`, `RetrievalTrace`, `AgentResponseTrace`, `HumanHandoffRequest`: auditoria y trazabilidad.

Tenant isolation:

- Toda query de datos del tenant debe filtrar por `tenant_id`.
- El payload no puede cambiar el tenant autenticado.
- En produccion el tenant debe venir de JWT RS256 o headers internos firmemente autenticados.

Indices:

- Documentos: `tenant_id,status`.
- Conversaciones: `tenant_id,status` y `tenant_id,channel,external_conversation_id`.
- Mensajes: `tenant_id,conversation_id,created_at`.
- Submissions: `tenant_id,form_id`.

Embeddings:

- El MVP guarda estructura para `DocumentEmbedding` con vector JSON.
- La implementacion productiva debe usar vector store por tenant y fuentes citables.
- Documentos contradictorios se resuelven por `status`, `priority`, `version` y fecha.
- En modo integrado, la version de `BusinessContextDocument` es asignada por Operational. La restriccion unica efectiva es `(tenant_id, filename, version)`.

Unificacion con operational:

- Auth crea/proyecta tenant.
- Operational provisiona runtime, schema fisico y variantes por industria.
- Agent Core pide persistencia/contexto por contrato interno a Operational.
- Agent Core nunca acepta `schema_name` desde cliente ni lo calcula desde headers.

Migraciones:

- Alembic no está configurado en este repositorio.
- El DDL productivo de contexto documental se gestiona desde `flowkron-operational-service`, que crea `business_context_documents`, `document_chunks`, `document_embeddings` y tablas asociadas en cada schema tenant.
- Este servicio solo crea las tablas automáticamente en base de datos local (SQLite/PG) para desarrollo aislado y tests unitarios cuando se activa `ALLOW_LOCAL_DB_BOOTSTRAP=true`.
