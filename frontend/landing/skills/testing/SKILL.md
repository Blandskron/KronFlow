---
name: testing
description: Usa esta skill al crear, ejecutar o diagnosticar pruebas de la landing.
---

# Testing

1. Lee [`docs/TESTING.md`](../../docs/TESTING.md).
2. Ejecuta `npm run build`.
3. Para smoke usa `docker compose --profile visual up --build --abort-on-container-exit`.
4. Revisa screenshots manualmente; no hay baseline automático.
5. No ejecutes ni reportes `npm test` como válido hasta configurar target/runner/specs.

No desactives assertions para ocultar regresiones.
