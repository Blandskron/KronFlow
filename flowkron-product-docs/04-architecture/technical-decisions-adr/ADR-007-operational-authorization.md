# ADR-007 — Autorización granular en Operational

Estado: Propuesto (`PROPOSED`)

## Contexto

Operational valida JWT humano, tenant, runtime y plan, pero los routers de dashboard no invocan actualmente `require_permission`.

## Decisión propuesta

Definir permisos requeridos por endpoint y validarlos server-side desde claims confiables o introspection/contrato Auth. El frontend seguirá siendo únicamente una capa UX.

## Criterios

- Matriz endpoint-permiso.
- Denegación cross-tenant.
- Tests 401/403 y entitlements.
- Estrategia ante claims obsoletos/revocación.
- Auditoría de acciones mutantes.
