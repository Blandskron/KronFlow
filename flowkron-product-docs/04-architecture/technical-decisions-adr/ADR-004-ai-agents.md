# ADR-004 — Agentes IA como capa operacional

Estado: Propuesto (`PROPOSED`)
Fecha de verificación: 2026-06-22

## Contexto

La visión propone agentes que interpreten conversaciones, clasifiquen leads, sugieran respuestas y ejecuten herramientas controladas.

## Propuesta

Diseñar una capa IA tenant-aware con contratos estructurados, límites, human-in-the-loop, auditoría, evaluación y control de costos.

## Estado actual

- No existe runtime/provider LLM.
- No existen prompts versionados, memoria IA, RAG, tools o evaluación.
- Operational registra `/agents`, pero `POST /agents/configure` devuelve 501.
- El frontend tiene onboarding de agente que intenta consumir ese stub.
- Textos de pricing sobre modelos no constituyen integración.

## Condiciones para aceptar

ADR de runtime/provider, threat model, contrato de agente/tools, persistencia, aislamiento, evaluación mínima, métricas/costos, fallback y pruebas.
