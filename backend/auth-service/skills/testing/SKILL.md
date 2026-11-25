---
name: testing
description: Usa esta skill al crear, modificar, ejecutar o diagnosticar pruebas del proyecto.
---

# Testing

1. Lee [`docs/TESTING.md`](../../docs/TESTING.md) y las invariantes de [`AGENTS.md`](../../AGENTS.md).
2. Busca casos similares en `apps/<app>/tests.py`.
3. Añade pruebas unitarias, de integración o seguridad proporcionales al cambio; prioriza permisos y aislamiento tenant.
4. Ejecuta el módulo relevante y, si el alcance lo permite, la suite:

```powershell
python manage.py test apps.<app>
python manage.py test
```

5. Reporta conteo y resultado reales. No borres/deshabilites pruebas para ocultar fallos ni declares cobertura no medida.
