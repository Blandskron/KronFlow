# Diseño de agentes

Versión: 1.2
Tipo: estado actual + objetivo
Estado: `PARTIAL`
Última verificación técnica: 2026-07-23

## Implementaciones actuales

### Agent Core

- `POST /api/v1/agent/messages`: contrato universal.
- `POST /api/v1/agent/simulate`: prueba desde App.
- Retrieval de contexto mediante Operational.
- Azure OpenAI opcional y fallback/handoff.
- Acciones preparadas mediante adapters no productivos.

## Contrato mínimo

Un agente productivo requiere:

- ID y versión;
- propósito y tareas permitidas;
- inputs/outputs tipados;
- prompt/model versionados;
- tools y permisos;
- límites, timeout y fallback;
- fuentes/provenance;
- métricas y costos;
- audit trail;
- handoff humano.

## Reglas

- El backend autoriza acciones; el LLM solo propone.
- Resolver tenant antes de recuperar contexto o ejecutar tools.
- No mezclar memoria entre tenants.
- Validar salida contra schema.
- Bloquear acciones críticas sin política y aprobación.
- Versionar prompt/model/tool junto a la traza.

## Brechas

- Sin registry de agentes/prompts.
- Sin tool executor autorizado.
- Sin evaluator/quality gate.
- Sin memoria productiva completa.

