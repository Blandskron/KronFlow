# Tool calling

Versión: 1.1
Tipo: estado actual + diseño objetivo
Estado: `PARTIAL`
Última verificación técnica: 2026-07-23

## Estado actual

- Agent Core devuelve acciones preparadas mediante adapters mock/locales; no ejecuta integraciones críticas productivas.
- Los nodos Postgres son integración legacy directa, no tool calling HTTP hacia Operational.
- No existe un registro central de tools, policy engine, autorización por tool ni auditoría unificada.

## Reglas para nuevas tools

Cada tool debe tener:

- contrato versionado;
- owner y consumidor;
- autenticación/autorización tenant-aware;
- schema de request/response;
- idempotencia;
- timeout, retry y circuit breaker;
- clasificación de datos;
- audit log sin secretos/PII innecesaria;
- límite de costo/rate;
- aprobación humana si produce efectos sensibles.

## Objetivo

Los gateways entregan mensajes; Agent Core decide una acción preparada; un executor autorizado llama APIs de dominio. Operational conserva la persistencia y la resolución tenant. Las nuevas tools no deben incorporar SQL directo en workflows.
