---
name: testing
description: Usa esta skill para validar sintaxis, salud e integración del stack Compose.
---

# Validación

1. Lee [`docs/VALIDATION.md`](../../docs/VALIDATION.md).
2. Ejecuta `docker compose config --quiet`; nunca muestres la salida expandida.
3. Si el usuario autoriza runtime, revisa `ps`, health endpoints y logs acotados.
4. Prueba dependencias y un flujo real; healthchecks solos no acreditan integración.
5. Declara claramente qué servicios o datos no se probaron.

No uses `down -v`, prune, credenciales reales en output ni regeneración de claves como prueba.
