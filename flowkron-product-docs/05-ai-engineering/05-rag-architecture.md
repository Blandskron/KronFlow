# Arquitectura RAG

Versión: 1.1
Tipo: Current State + Target Architecture
Estado de implementación: `PARTIAL`
Propietario previsto: `flowkron-agent-core` + persistencia resuelta por `flowkron-operational-service`
Última verificación técnica: 2026-07-09

## Estado actual

`flowkron-agent-core` tiene una implementacion integrada de RAG lexical para documentos y fuentes. La persistencia productiva de documentos/chunks no vive ni se provisiona en el core: Agent Core extrae texto, genera chunks y llama a Operational; Operational resuelve tenant/schema y persiste en el schema tenant. El simulador y `/agent/messages` recuperan fuentes desde Operational por API interna.

Lo que sigue pendiente como arquitectura objetivo es embeddings/vector store productivo, reranking, memoria durable, evaluacion automatizada y trazabilidad completa de groundedness.

## Flujo objetivo

```text
Fuente autorizada -> Agent Core valida/extrae/chunkea -> Operational resuelve tenant/schema -> documentos/chunks
Consulta -> Agent Core solicita retrieval por tenant -> Operational aplica filtros tenant + busqueda lexical actual
        -> contexto con fuentes -> LLM -> respuesta con citas/fallback humano
```

## Controles obligatorios

- ACL y tenant filter aplicados antes de retornar contexto.
- `schema_name` nunca viene del cliente ni del Agent Core; lo resuelve Operational.
- Provenance/cita de documento, versión y chunk.
- Defensa contra prompt injection en documentos.
- Eliminación/reindexación y retención trazables.
- Umbral de relevancia y respuesta “sin evidencia suficiente”.
- Evaluación de retrieval y groundedness.

Documentos de contexto empresarial y FAQ cargadas como documentos ya son fuentes conectadas. Inventario sigue disponible por endpoints operacionales/ingest y puede usarse como fuente candidata adicional, pero no reemplaza el contexto documental.
