---
name: release
description: Usa esta skill para evaluar una promoción del stack integrado hacia otro ambiente.
---

# Release

1. Lee [`docs/SECURITY.md`](../../docs/SECURITY.md) y [`docs/OPERATIONS.md`](../../docs/OPERATIONS.md).
2. No promociones el Compose local sin resolver secretos, TLS, exposición, backups, recursos y observabilidad.
3. Verifica imágenes, migraciones, CORS/SMTP, URLs compiladas, health e integración.
4. Exige backup/restore probado y rollback para cambios de datos, versión o claves.
5. Usa configuración administrada fuera del repositorio y validación silenciosa.

No despliegues, publiques, migres ni borres datos sin aprobación explícita.
