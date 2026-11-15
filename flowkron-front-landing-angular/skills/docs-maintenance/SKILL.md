---
name: docs-maintenance
description: Usa esta skill para mantener rutas, configuración, contenido y documentación agentica de la landing.
---

# Mantenimiento documental

1. Contrasta docs con componente, environment, Angular config, Docker/Nginx y smoke real.
2. Actualiza el documento canónico de `docs/`; `AGENTS.md` es la única fuente agentica y no se recrea `docs/agent/`.
3. Distingue comportamiento local, integración real y deuda pendiente.
4. Verifica enlaces, referencias obsoletas, fences y `git diff --check`.

No documentes `npm test`, backend de contacto o regresión visual como funcionales mientras no lo estén.
