# Arquitectura de inteligencia artificial

Versión: 1.1
Tipo: estado actual + arquitectura objetivo
Estado: `PARTIAL`
Última verificación técnica: 2026-07-23

## Estado actual

Existen dos piezas de IA:

1. `flowkron-agent-core`: runtime FastAPI independiente del canal, con contexto empresarial, plantillas, extracción documental, retrieval lexical, simulación, Groq opcional y fallback.


## Persistencia

En modo integrado:

- Agent Core no crea schemas;
- Operational guarda documentos y chunks en el schema tenant;
- Agent Core llama a Operational con tenant lógico y token interno;
- retrieval actual es lexical;
- las tablas de embeddings son estructura futura, no vector search productivo.

## Respuesta y fallback

Agent Core puede usar Groq cuando está configurado externamente. Debe devolver respuesta estructurada, confianza, fuentes, acción preparada y necesidad de handoff. Si el proveedor falla o no existe contexto suficiente, usa fallback seguro.

## Brechas

- Sin prompt registry versionado.
- Sin abstracción multi-provider completa.
- Sin memoria conversacional productiva completa.
- Sin evaluación automática ni dataset.
- Sin seguimiento de tokens/costos.
- Sin vector database.
- Sin tool executor productivo con autorización.
- Sin E2E de proveedor/canal.

## Arquitectura objetivo

```text
Gateway normaliza evento
  -> Agent Core valida tenant y política
  -> Operational entrega contexto tenant
  -> proveedor LLM genera salida estructurada
  -> policy/evaluator valida
  -> acciones críticas requieren autorización/humano
  -> Operational registra datos, métricas y auditoría
```

El objetivo requiere contratos versionados, threat model, evaluación, límites de costo, observabilidad, privacy review y human-in-the-loop.
