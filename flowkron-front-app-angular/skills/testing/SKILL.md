---
name: testing
description: Usa esta skill al crear, ejecutar o diagnosticar pruebas del frontend privado.
---

# Testing

1. Lee [`docs/TESTING.md`](../../docs/TESTING.md).
2. Ejecuta `npm run build`.
3. Para smoke público usa `docker compose --profile visual up --build --abort-on-container-exit`.
4. Revisa screenshots manualmente; no hay baselines ni E2E autenticado.
5. No ejecutes ni reportes `npm test` como válido hasta configurar target, runner y specs.

No uses credenciales/tokens reales ni desactives assertions para ocultar fallos.
