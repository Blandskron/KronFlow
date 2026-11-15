# Discovery

## Repositorios revisados

- `flowkron-auth-service`: Django IAM, tenants, RBAC, sesiones, OAuth, auditoria y emision de JWT.
- `flowkron-operational-service`: FastAPI, SQLAlchemy 2, PostgreSQL multi-schema por tenant, ingesta WhatsApp y datos operacionales.
- Los adaptadores externos conectan WhatsApp mediante la ingesta HTTP. Agent Core se mantiene independiente del canal.
- `flowkron-front-app-angular`: dashboard Angular y servicios frontend.
- `flowkron-front-landing-angular`: landing publica Angular.
- `flowkron-api-contracts`: OpenAPI, schemas JSON, errores y ADR de contratos.
- `flowkron-product-docs`: ADRs, arquitectura, seguridad, RAG, agentes, memoria, costos y operacion.
- `flowkron-deploy`: compose e infraestructura local.

## Arquitectura detectada

- Auth/IAM esta separado en Django.
- Operational usa FastAPI, SQLAlchemy ORM, Alembic y PostgreSQL.
- El modelo operacional vigente usa schema fisico por tenant, con `tenant_runtime` en tablas publicas.
- El dashboard consume APIs con JWT RS256.
- La ingesta WhatsApp usa `X-Tenant-Code` y `X-Ingest-Key` en operational.
- Los endpoints de agentes existentes en operational son stubs; el core nuevo debe asumir la inteligencia conversacional.

## Patrones que se deben respetar

- JWT RS256 emitido por `flowkron-auth-service`.
- `tenant_id` validado desde identidad confiable, no desde payload sin verificar.
- Separacion estricta por tenant.
- Contratos OpenAPI versionados y respuestas estandarizadas cuando se publiquen en `flowkron-api-contracts`.
- FastAPI + SQLAlchemy 2 + Pydantic settings.
- No acoplar logica de negocio a canales.

## Decisiones tecnicas existentes

- ADR-001 define PostgreSQL multi-schema.
- ADR-005 define modelo de confianza JWT.
- ADR-008 define gateway WhatsApp como adaptador.
- ADR-009 cubre runtime AI.
- ADR-010 centraliza contratos API.
- Las plantillas base de contexto se empaquetan dentro de `app/resources/context_templates` para que `flowkron-agent-core` las exponga tambien cuando corre en Docker. En desarrollo se puede usar la carpeta del monorepo o la variable `CONTEXT_TEMPLATE_ROOT`.
- Los documentos completados desde plantillas Word/PDF se deben subir por `POST /api/v1/context/documents/upload-file` como `multipart/form-data`; el core extrae texto antes de indexarlo para simulacion/RAG.
- El estado agregado de Contexto Empresarial se expone por `GET /api/v1/context/status`; el frontend no debe inferir progreso, estado del agente, ultima actualizacion ni capacidades de acciones documentales.
- En modo operacional, Agent Core consume `/internal/tenants/{tenant_id}/context/*` y desempaqueta el envelope estandar de Operational antes de validar sus propios `response_model`.
- Operational debe versionar documentos repetidos por `(tenant_id, filename)` para evitar violar `uniq_document_tenant_filename_version`; una segunda carga del mismo archivo debe retornar una nueva `version`.

## Contratos API encontrados

- `auth-service.openapi.yml`
- `operational-service.openapi.yml`
- `whatsapp-gateway.openapi.yml`
- Schemas AI: `ai-response`, `ai-source`, `retrieval-metadata`, `ai-safety`, `ai-usage`.
- Eventos: `contact-message-created`.

## Riesgos de integracion

- El core MVP conserva modelos SQLAlchemy como blueprint/test, pero no debe crear schemas ni tablas en produccion.
- Operational debe ser el unico servicio que resuelve donde escribir, incluyendo futuros schemas por industria.
- `flowkron-agent-core` no mantiene migraciones propias; el DDL real debe vivir en operational o en un migrator invocado por operational.
- La busqueda RAG es lexical y mock; embeddings/vector DB reales requieren decision de proveedor.
- La integracion con operational para crear leads, handoff o tickets aun no tiene contrato seguro en este servicio.
- `X-Tenant-Id` local no debe habilitarse en produccion.

## Supuestos no verificados

- Se verifico en Docker local que Operational persiste documentos en PostgreSQL y que una carga repetida del mismo filename retorna versiones consecutivas. No se verifico contra staging/produccion.
- No se verifico una clave publica JWT real.
- No se verifico vector store ni LLM productivo.

## Decisiones pendientes

- Contrato interno implementado para documentos, status y retrieval RAG mediante `/internal/tenants/{tenant_id}/context/*`; quedan pendientes memoria conversacional productiva, trazas persistidas en Operational, action logs y mutaciones documentales productivas.
- Definir proveedor de embeddings y vector store.
- Definir contrato final para acciones externas con operational/IAM.
- Definir permisos RBAC especificos para administrar contexto, reglas y simulaciones.
