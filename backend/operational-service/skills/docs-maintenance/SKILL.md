---
name: docs-maintenance
description: Usa esta skill para mantener rutas, configuración, datos y documentación agentica alineados con la implementación.
---

# Mantenimiento de documentación

1. Contrasta routers, schemas Pydantic, settings, modelos importados, servicios y scripts; no basta con inspeccionar nombres de archivo.
2. Actualiza `docs/API.md`, `DATA_MODEL.md`, `CONFIGURATION.md`, `SECURITY.md`, `OPERATIONS.md`, `TESTING.md` o `ARCHITECTURE.md` según corresponda.
3. Mantén `AGENTS.md` como única fuente agentica; adaptadores raíz mínimos y sin `docs/agent/` duplicado.
4. Distingue `tenant_models/operations.py` activo de módulos legacy no importados.
5. Valida OpenAPI cuando cambia HTTP, usa enlaces relativos y ejecuta `git diff --check`.

No copies secretos, rutas absolutas locales ni describas stubs como funcionalidad terminada.
