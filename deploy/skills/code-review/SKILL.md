---
name: code-review
description: Usa esta skill para revisar Compose, redes, volúmenes, dependencias y seguridad operacional.
---

# Revisión de orquestación

1. Revisa includes, interpolación, contextos relativos, nombres, imágenes y restart policy.
2. Contrasta puertos internos/publicados y URLs internas/públicas.
3. Audita dependencias/healthchecks sin confundir orden de inicio con resiliencia.
4. Clasifica named volumes y bind mounts; evalúa permisos, backup, migración y pérdida.
5. Detecta secretos/defaults inseguros, exposición host, falta de TLS/recursos/observabilidad.
6. Valida con `docker compose config --quiet`.

No leas `.env`/PEM ni ejecutes cambios destructivos durante una revisión.
