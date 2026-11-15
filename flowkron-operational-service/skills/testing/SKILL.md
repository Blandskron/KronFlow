---
name: testing
description: Usa esta skill al crear, ejecutar o diagnosticar pruebas y validaciones del servicio.
---

# Testing

1. Lee [`docs/TESTING.md`](../../docs/TESTING.md) y [`AGENTS.md`](../../AGENTS.md).
2. Ejecuta primero validaciones read-only:

```powershell
python -m compileall -q app scripts
```

3. No llames tests a los scripts de `scripts/`: escriben DB y algunos ejecutan `DROP SCHEMA ... CASCADE` sobre schemas temporales.
4. Solo ejecuta validaciones DB con autorización y `DATABASE_URL` confirmado hacia una base descartable.
5. Reporta exactamente lo ejecutado; hoy no existe suite automatizada.
