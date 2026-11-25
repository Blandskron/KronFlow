---
name: docs-maintenance
description: Usa esta skill para mantener contratos, configuración, datos y documentación agentica alineados con el repositorio.
---

# Mantenimiento de documentación

1. Contrasta documentación con URLs, serializers, modelos, settings, entrypoint y pruebas; no documentes diseño futuro como implementado.
2. Actualiza el documento canónico afectado: `API.md`, `DATA_MODEL.md`, `DEPLOYMENT.md`, `SECURITY.md`, `OPERATIONS.md`, `TESTING.md` o `ARCHITECTURE.md`.
3. Mantén `AGENTS.md` como única fuente agentica. `CLAUDE.md` y `GEMINI.md` son adaptadores mínimos; no recrees `docs/agent/`.
4. Si cambian contratos DRF, valida OpenAPI. Si cambia configuración, contrasta `.env.example` y settings sin leer `.env`.
5. Usa enlaces relativos, busca referencias obsoletas y ejecuta `git diff --check`.

Evita duplicar manuales, credenciales o rutas absolutas de una máquina local.
