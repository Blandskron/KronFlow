---
name: release
description: Usa esta skill para preparar un release del servicio operacional.
---

# Preparación de release

1. Lee [`docs/CONFIGURATION.md`](../../docs/CONFIGURATION.md) y el checklist de [`docs/OPERATIONS.md`](../../docs/OPERATIONS.md).
2. Valida sintaxis y artefactos:

```powershell
python -m compileall -q app scripts
docker compose config
docker compose build
```

3. Trata `migrate_all_tenants.py` como escritura masiva, no como check: requiere aprobación, backup, DB confirmada y plan de rollback.
4. Verifica OpenAPI, health/readiness, secretos, permisos DB, RBAC de borde, rate limit distribuido y smoke tests.

No publiques ni despliegues de forma autónoma. No muestres la salida expandida de Compose si contiene secretos.
