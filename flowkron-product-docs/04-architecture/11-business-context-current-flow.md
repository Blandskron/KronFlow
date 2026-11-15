# Flujo actual de Contexto Empresarial

Fecha: 2026-07-09
Tipo: Current State
Estado: `IMPLEMENTED`

## Resumen

El flujo implementado para contexto empresarial queda asi:

```text
flowkron-front-app-angular -> flowkron-agent-core -> flowkron-operational-service -> tenant schema PostgreSQL
```

## Responsabilidades

| Componente | Responsabilidad |
| --- | --- |
| `flowkron-front-app-angular` | Muestra plantillas, sube documentos, consulta status y ejecuta simulador |
| `flowkron-agent-core` | Expone API publica de contexto, extrae texto/chunks, desempaqueta `ApiResponse` de Operational y arma respuestas del agente |
| `flowkron-operational-service` | Resuelve tenant/schema, crea tablas tenant, persiste documentos/chunks, auto-versiona archivos repetidos y recupera fuentes lexicales |
| PostgreSQL tenant schema | Fuente de verdad de documentos, chunks y perfil de agente |

## Reglas vigentes

- El frontend privado descarga plantillas Word/PDF y sube documentos usando endpoints publicos de Agent Core.
- Agent Core no guarda documentos, chunks ni embeddings en memoria en el stack integrado.
- Operational asigna `version=max(version)+1` por `tenant_id + filename`; subir dos veces el mismo archivo crea una nueva version.
- Operational crea y mantiene las tablas tenant `business_context_documents`, `document_chunks`, `document_embeddings` y `tenant_agent_profiles`.
- Operational es el unico servicio que resuelve `tenant_id` logico a `schema_name`.
- Los tenants existentes requieren migracion/reprovisionamiento para recibir tablas nuevas.
- Las acciones `patch/delete/replace/retry_processing` se reportan deshabilitadas en modo integrado mientras Operational sea el duenio de la persistencia.

## Pendiente

- Embeddings/vector store productivo; retrieval actual es lexical sobre chunks activos.
- Evaluacion automatizada de respuestas RAG.
- Permisos RBAC granulares para administrar contexto.
- Contrato publico final de gestion de agentes mas alla del contexto documental.
