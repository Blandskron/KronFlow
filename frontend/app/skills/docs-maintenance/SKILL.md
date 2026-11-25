---
name: docs-maintenance
description: Usa esta skill para mantener rutas, APIs, configuración y documentación agentica del frontend privado.
---

# Mantenimiento documental

1. Contrasta docs con rutas, servicios, modelos, environment, Docker/Nginx y pruebas reales.
2. Actualiza el documento canónico bajo `docs/`; `AGENTS.md` es la única fuente agentica y no se recrea `docs/agent/`.
3. Distingue integración funcional, vista de solo lectura, placeholder y método sin UI.
4. Verifica enlaces, referencias obsoletas, fences y `git diff --check`.

No documentes unit tests, E2E autenticado, activación de planes o envío de mensajes como funcionales mientras no lo estén.
