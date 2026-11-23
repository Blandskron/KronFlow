# Evaluación de IA

Versión: 1.1
Tipo: arquitectura objetivo
Estado: `PARTIAL`
Última verificación técnica: 2026-11-23

Agent Core incluye un dataset sintético versionado y una suite reproducible para formato, fuentes, derivación, aislamiento básico y escenarios de proveedor simulado. El presupuesto por solicitud limita la entrada por caracteres y solicita un máximo de tokens de salida. La observación registra latencia y tokens cuando el proveedor los informa. Quedan pendientes la evaluación semántica con un modelo autorizado, los costos y la evidencia de release. [Evaluación del runtime](../../flowkron-agent-core/docs/agent/EVALUATION.md)

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

