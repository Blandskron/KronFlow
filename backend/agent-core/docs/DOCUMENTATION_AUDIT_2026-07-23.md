# Auditoría documental — 2026-07-23

Se contrastaron rutas FastAPI, configuración, tests y el contrato OpenAPI de Agent Core.

## Hechos confirmados

- El modo predeterminado es integrado: Operational conserva documentos, status y retrieval; Agent Core no provisiona schemas tenant.
- `X-Tenant-Id` es solo mecanismo local; producción requiere JWT RS256 emitido por Auth.
- Plantillas, carga de documentos y simulación están disponibles; formularios, reglas, conversaciones y trazas dependen de persistencia local o devuelven `501` en modo integrado.
- La suite `app/tests` existe, pero no valida proveedores reales ni el recorrido productivo completo.
- La especificación compartida es `openapi/services/agent-core.openapi.yml` v0.3.1.

Las suposiciones pendientes se deben registrar en `docs/agent/DISCOVERY.md`; no se inspeccionaron secretos.
