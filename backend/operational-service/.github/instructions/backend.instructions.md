---
applyTo: "**/{app}/**/*"
---

# Convenciones Backend

- **Arquitectura:** Sigue la estructura de directorios FastAPI (core -> api -> models -> schemas -> services).
- **Esquemas de datos:**
  - Los modelos del esquema común van bajo `public_models/`.
  - El esquema tenant activo está definido por `tenant_models/operations.py` y los imports de `tenant_models/__init__.py`; no importar los módulos legacy duplicados sin una migración deliberada.
- **Aislamiento Multi-Tenant:**
  - Toda query tenant debe usar `schema_translate_map` mediante los helpers existentes.
  - El `schema_name` persistido debe provenir del provisioning y de `sanitize_schema_name`; no aceptar schemas arbitrarios del request.
- **Autenticación:**
  - Las APIs de dashboard exigen validación JWT de `flowkron-auth-service`.
  - Las APIs de webhooks (el adaptador) exigen autenticación por cabeceras `X-Tenant-Code` y `X-Ingest-Key`.
  - No confundir autenticación con autorización: los permisos RBAC por endpoint aún no están conectados.
- **Compatibilidad de API:** No rompas contratos de API sin aprobación previa. Mantenga los schemas Pydantic de entrada/salida consistentes.
