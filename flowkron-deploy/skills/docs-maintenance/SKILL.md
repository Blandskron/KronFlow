---
name: docs-maintenance
description: Usa esta skill para mantener topología, configuración, operación y documentación agentica del stack Compose.
---

# Mantenimiento documental

1. Contrasta docs con los tres modelos Compose y `.env.example`, nunca con `.env` real.
2. Actualiza el documento canónico bajo `docs/`; `AGENTS.md` es la única fuente agentica y no se recrea `docs/agent/`.
3. Distingue defaults Compose, valores de la plantilla, puertos internos y publicados.
4. Verifica enlaces, referencias obsoletas, fences y `git diff --check`.
5. Valida Compose con `docker compose config --quiet`, sin capturar secretos.

No presentes este stack local como plataforma productiva ni recomiendes limpiezas destructivas.
