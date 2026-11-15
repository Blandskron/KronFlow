# Evaluación de IA

Versión: 1.1
Tipo: arquitectura objetivo
Estado: `NOT_IMPLEMENTED`
Última verificación técnica: 2026-07-23

No existe dataset versionado, harness, evaluadores automáticos ni quality gate.

## Evaluación mínima

- schema/formato;
- groundedness y citas;
- calidad de retrieval;
- prompt injection y exfiltración;
- PII;
- tool abuse;
- aislamiento cross-tenant;
- latencia/error/retry;
- tokens y costo;
- fallback y handoff.

## Gate

Cada cambio de prompt, modelo, retriever o tool debe compararse con un baseline sobre casos normales y adversariales. La ejecución debe registrar versión y permitir rollback.

## Artefactos requeridos

- dataset anonimizado;
- rúbricas;
- runner reproducible;
- métricas/umbrales;
- reporte por versión;
- regression gate CI;
- owner técnico.

