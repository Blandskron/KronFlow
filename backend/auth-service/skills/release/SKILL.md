---
name: release
description: Usa esta skill para preparar un release o validar empaquetado y despliegue.
---

# Preparación de release

1. Lee [`docs/DEPLOYMENT.md`](../../docs/DEPLOYMENT.md) y el checklist de [`docs/OPERATIONS.md`](../../docs/OPERATIONS.md).
2. Ejecuta las validaciones aplicables:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py collectstatic --noinput
docker compose config
docker compose build app
```

3. Verifica que secretos, settings de producción, migraciones, static files, health/readiness y smoke tests estén controlados.

No publiques imágenes ni despliegues de forma autónoma. Cambios CI/CD o infraestructura requieren autorización explícita.
